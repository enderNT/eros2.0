"""Los dos servicios externos, sustituidos por dobles en memoria.

Kapso y Calendly son **capas de transporte**, no la cosa que se está probando.
Mandar WhatsApp de verdad para leer una respuesta cuesta dinero, ensucia una
conversación real y hace la prueba irrepetible; pedirle horarios a Calendly de
verdad hace que el resultado dependa de la agenda de esta semana. Los dos dobles
de aquí implementan los *puertos* (`Channel`, `Calendar`) que los servicios ya
usan, así que todo lo que hay por debajo — agente, herramientas, webhooks,
outbox, recordatorios — corre exactamente igual que en producción.

Lo único que NO se sustituye es el modelo: el sistema bajo prueba es la
conversación, y una conversación con un modelo falso no prueba nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from agente.domain.errors import CalendlyError, SlotTakenError
from agente.ports.calendar import Booking, CalendarSlot
from agente.ports.channel import ConversationList, ConversationRow


@dataclass(frozen=True, slots=True)
class SentMessage:
    """Un mensaje que en producción habría salido por WhatsApp."""

    to: str
    text: str
    at: datetime
    message_id: str


class RecordingChannel:
    """`Channel` que guarda en una lista en vez de llamar a Kapso.

    Devuelve un id sintético para que `messages.add_outbound` tenga qué
    guardar; el resto del sistema no distingue este id de uno de Kapso.
    """

    def __init__(self) -> None:
        self.sent: list[SentMessage] = []
        self._counter = 0
        # El panel lista lo que Kapso conoce, no lo que hay en nuestra base. Sin
        # esto el contacto de prueba no aparecería en /admin y los casos que
        # comprueban el panel medirían el doble en vez del panel.
        self.conversations: dict[str, ConversationRow] = {}

    def register(self, phone: str, *, name: str | None = "Paciente De Prueba") -> None:
        self.conversations[phone] = ConversationRow(
            conversation_id=f"eval-{phone[-4:]}",
            contact_name=name,
            contact_phone=phone,
            last_message_text=None,
            last_activity_at=datetime.now(UTC),
            status="active",
        )

    async def send_text(self, phone_number_id: str, to: str, body: str) -> str:
        self._counter += 1
        message_id = f"eval-out-{self._counter:04d}"
        now = datetime.now(UTC)
        self.sent.append(SentMessage(to, body, now, message_id))
        previa = self.conversations.get(to)
        self.conversations[to] = ConversationRow(
            conversation_id=previa.conversation_id if previa else f"eval-{to[-4:]}",
            contact_name=previa.contact_name if previa else None,
            contact_phone=to,
            last_message_text=body,
            last_activity_at=now,
            status="active",
        )
        return message_id

    async def list_conversations(
        self, phone_number_id: str, *, cursor: str | None = None, limit: int = 20
    ) -> ConversationList:
        return ConversationList(
            conversations=list(self.conversations.values())[:limit], next_cursor=None
        )

    async def aclose(self) -> None:
        return None

    def since(self, index: int) -> list[SentMessage]:
        return self.sent[index:]


@dataclass
class FakeCalendar:
    """`Calendar` determinista, con la misma forma que devuelve Calendly.

    Genera huecos en horas fijas de días hábiles, en la zona de la clínica, para
    que un caso ejecutado hoy y el mismo caso ejecutado el mes que viene ofrezcan
    la misma cuadrícula. `booking_url` imita el enlace por hueco de Calendly:
    es lo que hace que `agendar_cita` pueda colgarle el `utm_content`, y sin eso
    ni el seguimiento ni la atribución de la reserva se podrían probar.

    `mark_booked` / `mark_free` existen para reproducir la única propiedad de
    Calendly que un caso necesita observar: un hueco reservado deja de ofrecerse,
    y **sólo** vuelve a ofrecerse si algo lo cancela. Nada del código llama a
    `mark_free`; lo llama el arnés al simular `invitee.canceled`. Que un hueco se
    quede muerto tras un "al final no puedo" no es un defecto del doble: es
    exactamente lo que pasa en producción.

    `book` / `cancel` reproducen las reglas de escritura **verificadas** contra
    la API real el 2026-08-22, y sólo ésas:

    * reservar un hueco ya ocupado levanta `SlotTakenError` (la API responde 400
      `already_filled`): Calendly arbitra, así que la doble reserva no existe;
    * cancelar libera el hueco en el acto, y por eso reagendar es cancelar y
      volver a reservar — no hay endpoint de reagendado;
    * cancelar dos veces no falla (la API responde 403 `already canceled`, que
      para nosotros es el estado deseado), y cancelar algo desconocido sí.

    Lo que **no** se imita es qué contesta la API a un horario fuera de
    disponibilidad: nunca se llegó a observar, y un doble que se lo invente
    haría pasar casos que en producción fallarían.

    Y una divergencia que conviene tener presente: aquí cancelar libera el hueco
    de forma determinista, siempre. Contra la API real se midió reaparición
    inmediata en dos de tres intentos, y en el tercero el hueco tardó en volver
    a ofrecerse. Un caso que cancele y pregunte por disponibilidad en el mismo
    aliento pasará siempre aquí y podrá parpadear en modo real.
    """

    timezone: str = "America/Mexico_City"
    hours_local: tuple[int, ...] = (10, 12, 16, 18)
    duration_minutes: int = 60
    weekdays_only: bool = True
    base_url: str = "https://calendly.test/clinica/valoracion"
    booked: set[datetime] = field(default_factory=set)
    extra: set[datetime] = field(default_factory=set)
    lead: timedelta = timedelta(minutes=5)
    events_url: str = "https://calendly.test/scheduled_events"
    bookings: dict[str, datetime] = field(default_factory=dict)
    canceled: set[str] = field(default_factory=set)
    counter: int = 0

    def add_slot(self, start_utc: datetime) -> CalendarSlot:
        """Ofrecer un hueco arbitrario, para casos que necesitan una cita en minutos."""
        moment = _floor(start_utc)
        self.extra.add(moment)
        return self._slot(moment)

    def mark_booked(self, start_utc: datetime) -> None:
        self.booked.add(_floor(start_utc))

    def mark_free(self, start_utc: datetime) -> None:
        self.booked.discard(_floor(start_utc))

    def is_booked(self, start_utc: datetime) -> bool:
        return _floor(start_utc) in self.booked

    async def availability(self, start: datetime, end: datetime) -> list[CalendarSlot]:
        floor = max(start, datetime.now(UTC) + self.lead)
        moments = sorted(self._grid(floor, end) | {m for m in self.extra if floor < m <= end})
        return [self._slot(moment) for moment in moments if moment not in self.booked]

    async def book(
        self,
        slot: CalendarSlot,
        *,
        name: str,
        email: str,
        timezone: str,
        phone: str,
    ) -> Booking:
        moment = _floor(slot.start_utc)
        if moment in self.booked:
            raise SlotTakenError("slot already booked")
        self.booked.add(moment)
        # Un id nuevo por reserva, aunque sea el mismo hueco de una cita
        # cancelada: Calendly acuña un uuid cada vez, y el índice único de
        # `calendly_event_id` rechazaría un id repetido.
        self.counter += 1
        event_id = f"{self.events_url}/{self.counter:04d}"
        self.bookings[event_id] = moment
        return Booking(event_id=event_id, invitee_id=f"{event_id}/invitees/1", start_utc=moment)

    async def cancel(self, event_id: str, *, reason: str = "") -> None:
        if event_id in self.canceled:
            return
        moment = self.bookings.get(event_id)
        if moment is None:
            raise CalendlyError("unknown event")
        self.canceled.add(event_id)
        self.booked.discard(moment)

    async def create_invitee(self, slot: CalendarSlot, name: str, email: str) -> str:
        return slot.booking_url

    async def aclose(self) -> None:
        return None

    def _grid(self, start: datetime, end: datetime) -> set[datetime]:
        zone = ZoneInfo(self.timezone)
        local = start.astimezone(zone)
        moments: set[datetime] = set()
        for offset in range(0, 32):
            day = (local + timedelta(days=offset)).date()
            if self.weekdays_only and day.weekday() >= 5:
                continue
            for hour in self.hours_local:
                moment = datetime(day.year, day.month, day.day, hour, tzinfo=zone).astimezone(UTC)
                if start < moment <= end:
                    moments.add(moment)
        return moments

    def _slot(self, start_utc: datetime) -> CalendarSlot:
        stamp = start_utc.strftime("%Y%m%dT%H%M%SZ")
        return CalendarSlot(
            id=start_utc.isoformat().replace("+00:00", "Z"),
            start_utc=start_utc,
            end_utc=start_utc + timedelta(minutes=self.duration_minutes),
            booking_url=f"{self.base_url}/{stamp}",
        )


def _floor(moment: datetime) -> datetime:
    """UTC al segundo: la clave con la que un hueco se identifica en el doble."""
    return moment.astimezone(UTC).replace(microsecond=0)
