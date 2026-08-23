"""One gentle nudge to somebody who got interested and then went quiet.

Deliberately **not** the same thing as `BookingFollowups`, and deliberately not
merged with it. They look alike — one outbox row, one message, cancel when the
patient writes back — but they answer different questions at different moments:

* `BookingFollowups` asks "¿pudiste agendar tu cita?" of somebody who was already
  holding a specific time. There is a slot to name and a booking to chase.
* This one asks nothing so specific, because there is nothing specific to ask
  about. The person asked what therapy costs, or what the clinic treats, and
  never got as far as a time. Naming a slot here would invent one.

Merging them would mean one delay setting for two situations that want different
ones — you chase an abandoned booking sooner than you re-approach somebody who
was only browsing — and one panel control for two decisions the clinic makes
separately. So: same shape, separate everything.

**Who gets one.** Anybody the bot replies to who has no scheduled appointment.
That is broader than "asked about booking" on purpose: the case this exists for
(C01) is somebody who only ever asked the price, and a narrower trigger would
miss exactly them. The narrowing happens later and by facts rather than by
guesswork — a patient who books is skipped, a muted or escalated contact is
skipped, and anybody who writes back cancels their own follow-up before it fires.

**Why this cannot loop.** Scheduling is driven by `on_outbound`, which only fires
when `InboundService` answers a patient. The follow-up itself goes out through
the channel directly, so sending one never schedules the next. Each silence earns
at most one nudge.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from ..domain.contacts import ContactKey
from ..domain.errors import KapsoError
from ..ports.channel import Channel
from ..ports.store import (
    AppointmentsRepository,
    MessagesRepository,
    MutesRepository,
    OutboxRepository,
    OutboxRow,
)

log = logging.getLogger(__name__)

KIND = "interest_followup"

FOLLOWUP_TEXT = (
    "Hola, ¿sigues por ahí? Quedé al pendiente de tu consulta."
    " Si quieres, te paso horarios para la cita de valoración,"
    " y si prefieres pensarlo con calma también está bien 😊"
)


class InterestFollowups:
    def __init__(
        self,
        *,
        outbox: OutboxRepository,
        appointments: AppointmentsRepository,
        messages: MessagesRepository,
        mutes: MutesRepository,
        channel: Channel,
        delay_minutes: Callable[[], int] = lambda: 60,
        enabled: Callable[[], bool] = lambda: True,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._outbox, self._appointments = outbox, appointments
        self._messages, self._mutes, self._channel = messages, mutes, channel
        self._delay_minutes, self._enabled, self._now = delay_minutes, enabled, now

    def schedule_from_outbound(self, key: ContactKey, text: str, sent_at: datetime) -> None:
        """Arm the nudge after the bot speaks, unless the contact already booked.

        `text` is ignored, and the signature keeps it only so this can be wired
        into the same `on_outbound` seam as the booking follow-up. There is
        nothing to read in it: unlike a booking link, an interested silence looks
        the same whatever the bot happened to say.
        """
        if not self._enabled() or self._has_appointment(key):
            return
        self._outbox.schedule_interest_followup(
            key, FOLLOWUP_TEXT, sent_at + timedelta(minutes=self._delay_minutes())
        )

    def cancel_for_contact(self, key: ContactKey) -> None:
        """The patient wrote back, so the silence this was waiting on is over."""
        self._outbox.cancel_for_contact(key, kind=KIND)

    def drop_pending(self) -> None:
        """Vaciar la cola entera, para cuando la clínica apaga esta conducta.

        Apagar tiene que borrar lo encolado, no sólo dejar de encolar. Un aviso
        que sobrevive al interruptor sale en cuanto alguien lo vuelva a encender,
        y para entonces el silencio que lo motivó es historia antigua.
        """
        self._outbox.cancel_kind(KIND)

    async def send_due(self, now: datetime | None = None) -> None:
        if not self._enabled():
            return
        moment = now or self._now()
        for row in self._outbox.due(moment, kind=KIND):
            if not self._outbox.consume(row.id, moment):
                continue
            await self._deliver(row, moment)

    async def send_now(self, key: ContactKey) -> str:
        """The panel's "enviar seguimiento ahora" button, for one contact."""
        if not self._enabled():
            return "disabled"
        row = self._outbox.pending_interest_followup(key)
        if row is None:
            return "missing"
        now = self._now()
        if not self._outbox.consume(row.id, now):
            return "already_sent"
        return await self._deliver(row, now)

    async def _deliver(self, row: OutboxRow, now: datetime) -> str:
        """Send, unless the world moved on while the row was waiting.

        Both checks happen here rather than at scheduling time because both can
        become true in between, and a follow-up is only ever wrong at the moment
        it would arrive: asking "¿sigues por ahí?" of somebody who booked
        yesterday, or of a conversation a human already took over.
        """
        if self._mutes.is_bot_muted(row.key, now):
            return "muted"
        if self._has_appointment(row.key):
            return "booked"
        try:
            message_id = await self._channel.send_text(
                row.key.phone_number_id, row.key.contact_phone, row.text
            )
        except KapsoError:
            log.error("interest_followup_send_failed")
            return "failed"
        self._messages.add_outbound(row.key, message_id, row.text, now)
        return "sent"

    def _has_appointment(self, key: ContactKey) -> bool:
        return any(item.status == "scheduled" for item in self._appointments.for_contact(key))
