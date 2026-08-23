"""Where a Calendly slot becomes a real appointment.

Two doors lead here. `book_for_contact` is the front one: `agendar_cita` reserves
through the Scheduling API and this writes the row. `handle` is the back one —
Calendly's webhook, which reports bookings we did not make: the clinic adding
somebody by hand, or a host-side reschedule.

There used to be a third. The bot handed out a booking page carrying an opaque
token, and this service resolved that token to find out whose booking had come
back. Booking on the patient's behalf removed the question, and the token, the
link and the follow-up that chased it went with it (migration 0009).

Two properties matter more than anything else here:

* **Idempotency.** Calendly retries a delivery it thinks failed. The same
  `calendly_event_id` must never produce a second appointment row or a second
  WhatsApp message — a patient receiving "tu cita quedó confirmada" twice reads
  it as two appointments.
* **Silence on a booking we cannot attribute.** Without a token the only handle
  left is the phone number, and it has to belong to a contact we already know.
  Anything else is somebody who booked from the public page.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..domain.contacts import ContactKey
from ..domain.errors import CalendlyError, KapsoError, StoreError
from ..domain.scheduling import Slot, slot_label
from ..ports.calendar import Calendar, CalendarSlot
from ..ports.channel import Channel
from ..ports.store import (
    AppointmentRow,
    AppointmentsRepository,
    ContactsRepository,
    MessagesRepository,
    OutboxRepository,
    Profile,
)
from .reminders import AppointmentReminders

log = logging.getLogger(__name__)

CREATED = "invitee.created"
CANCELED = "invitee.canceled"

CANCELED_TEXT = "Tu cita quedó cancelada. Si quieres, te paso otros horarios para reagendar."


def moved_text(slot_utc: datetime, timezone: str, now: datetime) -> str:
    """El aviso de que la cita cambió de hora sin que el paciente hiciera nada.

    Se separa de la confirmación normal porque no es lo mismo: aquí la persona
    no pidió nada, y decirle "tu cita quedó confirmada" la dejaría sin saber que
    la hora que tenía apuntada ya no vale.
    """
    label = slot_label(Slot(slot_utc, slot_utc), ZoneInfo(timezone), now)
    return (
        f"Tuvimos que mover tu cita: quedó para {label}."
        " Si ese horario nuevo no te sirve, escríbeme y lo cambiamos."
    )


def confirmation_text(slot_utc: datetime, timezone: str, now: datetime, address: str) -> str:
    """The patient-facing confirmation, in clinic local time.

    The address is only mentioned when it is actually configured: an invented
    address is worse than no address.
    """
    label = slot_label(Slot(slot_utc, slot_utc), ZoneInfo(timezone), now)
    parts = [_sentence(f"¡Listo! Tu cita quedó confirmada: {label}")]
    if address:
        parts.append(_sentence(f"La dirección es {address}"))
    parts.append("Si necesitas cambiarla, escríbeme por aquí.")
    return " ".join(parts)


def _sentence(text: str) -> str:
    """Close the sentence without doubling the period.

    Both halves can already end in one: the time label ends in "p. m." and the
    configured address is written by a human who may or may not punctuate it.
    """
    return text if text.rstrip().endswith((".", "!", "?")) else f"{text}."


class BookingService:
    def __init__(
        self,
        *,
        appointments: AppointmentsRepository,
        contacts: ContactsRepository,
        messages: MessagesRepository,
        outbox: OutboxRepository,
        channel: Channel,
        reminders: AppointmentReminders | None = None,
        calendar: Calendar | None = None,
        invitee_email: str = "",
        phone_number_id: str = "",
        timezone: str,
        address: str = "",
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._appointments = appointments
        self._contacts, self._messages = contacts, messages
        self._outbox, self._channel = outbox, channel
        self._reminders = reminders
        self._calendar, self._invitee_email = calendar, invitee_email
        self._phone_number_id = phone_number_id
        self._timezone, self._address, self._now = timezone, address, now

    async def book_for_contact(self, key: ContactKey, slot: CalendarSlot) -> datetime:
        """Reserve on the patient's behalf and record it. Returns the slot booked.

        **Reserving replaces.** If the contact already has a scheduled appointment,
        it is released once the new one exists. That rule lives here rather than in
        the model's instructions on purpose: "move my appointment" is the single
        most likely thing a patient asks, and leaving it to the model to chain a
        cancel and a book correctly is how you end up with two appointments, two
        blocked hours and two reminders (the old C09 hueco). Code decides.

        The order matters and is not the intuitive one: the new booking happens
        **first**. If it fails — someone took the slot in the meantime — the patient
        keeps the appointment they had. Cancelling first would leave them with
        nothing when the second half fails.

        No message is sent from here. The tool result goes back to the model, which
        tells the patient in its own reply; sending from here too would say it twice.
        """
        if self._calendar is None:
            raise CalendlyError("no calendar configured")
        now = self._now()
        profile = self._profile(key, now)
        booking = await self._calendar.book(
            slot,
            name=profile.name or "Paciente",
            email=self._invitee_email or profile.email or "",
            timezone=self._timezone,
            phone=key.contact_phone,
        )
        previas = self.scheduled_for(key)
        self._contacts.ensure_contact(key, now)
        self._appointments.add(key, booking.event_id, booking.start_utc, now)
        # Mover una cita no es una cita más. `appointment_count` cuenta veces que
        # el paciente viene, y sumar por cada reagendado lo convertiría en "veces
        # que cambió de idea", que es otra cosa y nadie la quiere.
        self._contacts.save_profile(
            replace(
                profile,
                kind="patient",
                appointment_count=profile.appointment_count + (0 if previas else 1),
                next_appointment_utc=booking.start_utc,
                updated_at=now,
            )
        )
        if self._reminders is not None:
            self._reminders.schedule(key, booking.event_id, booking.start_utc, now)
        for previa in previas:
            await self._release(previa.calendly_event_id, now, reason="cita movida por el paciente")
        return booking.start_utc

    async def cancel_for_contact(self, key: ContactKey, *, reason: str = "") -> datetime | None:
        """Release the contact's appointment. `None` when there was nothing to release.

        That `None` is the whole answer to "cancel my Thursday appointment" from
        somebody who has none: the caller says so instead of inventing a booking to
        cancel (C15).
        """
        if self._calendar is None:
            raise CalendlyError("no calendar configured")
        now = self._now()
        vigentes = self.scheduled_for(key)
        if not vigentes:
            return None
        cita = vigentes[0]
        await self._release(cita.calendly_event_id, now, reason=reason)
        self._clear_next_appointment(key, now)
        return cita.slot_utc

    async def _release(self, event_id: str, now: datetime, *, reason: str) -> None:
        """Cancel in Calendly and locally, in that order.

        Marking it cancelled here is also what makes the `invitee.canceled` webhook
        that Calendly fires back at us a no-op: `_canceled` sees the status is
        already `canceled` and returns. The patient gets one message, not two.
        """
        assert self._calendar is not None
        await self._calendar.cancel(event_id, reason=reason)
        self._appointments.update_status(event_id, "canceled", now)
        self._outbox.cancel_for_appointment(event_id)

    def scheduled_for(self, key: ContactKey) -> list[AppointmentRow]:
        """Las citas vigentes del contacto. Pública porque las herramientas
        necesitan saber si hay algo que mover o que cancelar antes de actuar."""
        return [item for item in self._appointments.for_contact(key) if item.status == "scheduled"]

    async def handle(self, event: str, payload: dict[str, Any]) -> None:
        if event == CREATED:
            await self._created(payload)
        elif event == CANCELED:
            await self._canceled(payload)
        else:
            log.info("calendly_event_ignored", extra={"event": event})

    async def _created(self, payload: dict[str, Any]) -> None:
        event_uri = str(payload.get("event") or "")
        if not event_uri:
            log.warning("calendly_payload_incomplete", extra={"event": CREATED})
            return
        if self._appointments.find(event_uri) is not None:
            log.info("calendly_delivery_duplicate", extra={"event": CREATED})
            return
        await self._created_by_phone(event_uri, payload)

    async def _created_by_phone(self, event_uri: str, payload: dict[str, Any]) -> None:
        """A booking we did not make ourselves. Usually the clinic.

        Once we book on the patient's behalf we write their WhatsApp number into
        Calendly's phone question ourselves, and Calendly carries the answers over
        when the host reschedules. So a rescheduled event arrives carrying a number
        we put there — which is the difference between attributing and guessing,
        and the reason this is not the old `booking_unlinked` discard.

        The bar stays high on purpose: the number must belong to a contact we
        already know. An unrecognised one is somebody who booked from the public
        page, and confirming that to a patient of ours would be the exact mistake
        the silent discard was protecting against.
        """
        key = self._key_from_phone(payload)
        if key is None:
            log.info("calendly_booking_unlinked", extra={"attributed": False})
            return
        now = self._now()
        slot = _start_time(payload)
        if slot is None:
            log.info("calendly_booking_unlinked", extra={"attributed": False, "reason": "no_slot"})
            return
        try:
            self._appointments.add(key, event_uri, slot, now)
        except StoreError:
            log.info("calendly_delivery_duplicate", extra={"event": CREATED})
            return
        self._save_profile(key, slot, now, payload)
        if self._reminders is not None:
            self._reminders.schedule(key, event_uri, slot, now)
        log.info("calendly_booking_attributed_by_phone")
        # Siempre "tuvimos que mover tu cita", aunque el payload no distinga una
        # mudanza de un alta hecha a mano por la clínica. Se probó decidirlo por
        # si el contacto ya tenía cita, y es falso justo cuando importa: en un
        # reagendado Calendly manda primero `canceled` y luego `created`, así que
        # para cuando llega el alta ya no queda ninguna cita a la vista.
        await self._notify(key, moved_text(slot, self._timezone, now))

    def _key_from_phone(self, payload: dict[str, Any]) -> ContactKey | None:
        if not self._phone_number_id:
            return None
        for value in _phone_answers(payload):
            digits = _phone_digits(value)
            if len(digits) < 10:
                continue
            key = ContactKey(self._phone_number_id, f"+{digits}")
            if self._contacts.get_profile(key) is not None:
                return key
        return None

    async def _canceled(self, payload: dict[str, Any]) -> None:
        event_uri = str(payload.get("event") or "")
        existing = self._appointments.find(event_uri) if event_uri else None
        if existing is None:
            log.info("calendly_cancel_unknown")
            return
        if existing.status == "canceled":
            log.info("calendly_delivery_duplicate", extra={"event": CANCELED})
            return
        now = self._now()
        self._appointments.update_status(event_uri, "canceled", now)
        self._outbox.cancel_for_appointment(event_uri)
        self._clear_next_appointment(existing.key, now)
        await self._notify(existing.key, CANCELED_TEXT)

    def _save_profile(
        self, key: ContactKey, slot: datetime, now: datetime, payload: dict[str, Any]
    ) -> None:
        current = self._profile(key, now)
        self._contacts.save_profile(
            replace(
                current,
                name=current.name or _clean(payload.get("name")),
                email=current.email or _clean(payload.get("email")),
                kind="patient",
                appointment_count=current.appointment_count + 1,
                next_appointment_utc=slot,
                updated_at=now,
            )
        )

    def _clear_next_appointment(self, key: ContactKey, now: datetime) -> None:
        current = self._profile(key, now)
        self._contacts.save_profile(replace(current, next_appointment_utc=None, updated_at=now))

    def _profile(self, key: ContactKey, now: datetime) -> Profile:
        existing = self._contacts.get_profile(key)
        if existing is not None:
            return existing
        return Profile(
            key=key,
            name=None,
            email=None,
            kind="prospect",
            timezone=None,
            appointment_count=0,
            last_appointment_utc=None,
            next_appointment_utc=None,
            handoff_state="bot",
            updated_at=now,
        )

    async def _notify(self, key: ContactKey, text: str) -> None:
        try:
            outbound_id = await self._channel.send_text(
                key.phone_number_id, key.contact_phone, text
            )
        except KapsoError:
            # The appointment is already recorded; losing the notification must
            # not lose the booking.
            log.error("calendly_notify_failed")
            return
        self._messages.add_outbound(key, outbound_id, text, self._now())


def _start_time(payload: dict[str, Any]) -> datetime | None:
    value = (payload.get("scheduled_event") or {}).get("start_time")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _clean(value: Any) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _matches_contact_phone(payload: dict[str, Any], contact_phone: str) -> bool:
    """Match the required Calendly phone answer to the WhatsApp identity.

    Calendly questions are clinic-configurable, so we intentionally only read
    answers whose label says phone/cell/WhatsApp. Matching the final ten
    digits supports a Mexican local entry (``55 1234 5678``) as well as its
    E.164 form while avoiding arbitrary numeric answers such as an age.
    """
    expected = _phone_digits(contact_phone)
    if len(expected) < 10:
        return False
    for value in _phone_answers(payload):
        candidate = _phone_digits(value)
        if candidate and (candidate == expected or candidate[-10:] == expected[-10:]):
            return True
    return False


def _phone_answers(payload: dict[str, Any]) -> list[object]:
    """Los campos del payload que dicen ser un teléfono, y sólo ésos.

    Las preguntas de Calendly las configura la clínica, así que se leen únicamente
    las que se llaman como un teléfono: una respuesta numérica cualquiera —una
    edad, un código postal— no debe entrar aquí.
    """
    values: list[object] = [payload.get("phone"), payload.get("phone_number")]
    for item in payload.get("questions_and_answers") or []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").lower()
        if any(word in question for word in ("tel", "phone", "cel", "whatsapp", "móvil", "movil")):
            values.append(item.get("answer"))
    return values


def _phone_digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or "")).removeprefix("00")
