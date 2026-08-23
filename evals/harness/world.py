"""`World`: la aplicación real, arrancada en proceso, manejable desde un test.

Qué es real aquí: la app de FastAPI completa (`create_app`), sus rutas de
webhook con verificación de firma, el servicio de entrada con su debounce, el
clasificador de crisis, el agente con sus cuatro herramientas, la base SQLite
con sus migraciones, el outbox, los recordatorios, el seguimiento y el panel.

Qué está sustituido: sólo Kapso y Calendly (ver `fakes.py`).

Qué está bajo control del test, en vez de del reloj: el disparo de lo que
vence. `_run_followups` de la app despierta cada `booking_followup_poll_seconds`
y llama a `send_due()` con la hora real; aquí ese intervalo se pone en una hora
para que no salte solo, y el test dispara `fire_due(at=...)` con el momento que
quiera. No es un truco: `send_due(now)` acepta el instante como argumento
justamente para esto, así que se ejecuta el mismo código, sin esperar 24 horas
ni falsear el reloj del proceso.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import sqlite3
import uuid
from collections.abc import Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch
from zoneinfo import ZoneInfo

import httpx

from agente import app as app_module
from agente.adapters.store.appointments import SqliteAppointmentsRepository
from agente.adapters.store.contacts import SqliteContactsRepository
from agente.adapters.store.mutes import SqliteMutesRepository
from agente.config import load_settings
from agente.domain.contacts import ContactKey
from agente.domain.scheduling import Slot, slot_label

from .calendario import CalendarioFalso, CalendlyEnVivo, crear_calendario, modo_configurado
from .fakes import RecordingChannel

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "evals" / ".runs"

# Número de prueba. Nunca sale de la máquina: el canal es un doble.
CONTACT = "+525555550100"
PHONE_NUMBER_ID = "eval-phone-number"
KAPSO_SECRET = "eval-kapso-secret"
CALENDLY_SIGNING_KEY = "eval-calendly-signing-key"


@dataclass(frozen=True, slots=True)
class Exchange:
    """Un turno: lo que se mandó y lo que salió, con las herramientas que se usaron."""

    sent: str
    replies: tuple[str, ...]
    tools: tuple[str, ...] = ()
    origin: str = "paciente"
    # Lo que devolvieron las herramientas en este turno. Sin esto el juez no
    # puede distinguir un precio recuperado de la wiki de uno inventado: sólo ve
    # el texto final, donde los dos se parecen exactamente igual.
    evidencia: tuple[tuple[str, str], ...] = ()

    @property
    def reply(self) -> str:
        return "\n".join(self.replies)


@dataclass(frozen=True, slots=True)
class Appointment:
    slot_utc: datetime
    status: str
    event_uri: str


@dataclass(frozen=True, slots=True)
class Pending:
    kind: str
    due_at: datetime
    sent_at: datetime | None
    text: str
    event_uri: str | None

    @property
    def sent(self) -> bool:
        return self.sent_at is not None


@dataclass(frozen=True, slots=True)
class Reserva:
    """Cómo acabó existiendo la cita de una precondición.

    `por_el_sistema` es el dato que separa el mundo viejo del nuevo: `True` si la
    cita la creó `agendar_cita` durante la conversación, `False` si el arnés tuvo
    que simular el enlace de Calendly porque el sistema no reservó solo. Los
    casos lo publican como criterio en vez de reventar: una precondición que no
    se cumple es un hallazgo, no un error del arnés.
    """

    event_uri: str
    slot_utc: datetime
    por_el_sistema: bool


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Lo que la base dice del contacto. Esto manda sobre lo que diga el chat."""

    appointments: tuple[Appointment, ...]
    outbox: tuple[Pending, ...]
    muted: bool
    mute_reason: str | None
    profile: dict[str, Any] | None
    tokens: tuple[str, ...]

    @property
    def scheduled(self) -> tuple[Appointment, ...]:
        return tuple(item for item in self.appointments if item.status == "scheduled")

    @property
    def reminders(self) -> tuple[Pending, ...]:
        return tuple(item for item in self.outbox if item.kind == "appointment_reminder")

    @property
    def followups(self) -> tuple[Pending, ...]:
        """Seguimientos **de reserva**: los que cuelgan de un horario ya ofrecido."""
        return tuple(item for item in self.outbox if item.kind == "booking_followup")

    @property
    def seguimientos_interes(self) -> tuple[Pending, ...]:
        """Seguimientos **de interés**: los de quien nunca llegó a tener un horario.

        Separado de `followups` porque un caso que los sume no está midiendo nada:
        ver uno u otro dice cosas distintas sobre en qué punto se enfrió la
        conversación.
        """
        return tuple(item for item in self.outbox if item.kind == "interest_followup")


class World:
    def __init__(self, name: str, app, client, channel, calendar, settings, modo) -> None:
        self.name = name
        self.app = app
        self.client: httpx.AsyncClient = client
        self.channel: RecordingChannel = channel
        self.calendar: CalendarioFalso | CalendlyEnVivo = calendar
        self.settings = settings
        # `fake` o `real`. Queda en el informe de cada caso: un resultado no se
        # puede comparar con otro sin saber cuánto sistema real había detrás.
        self.modo_calendario = modo
        self.key = ContactKey(PHONE_NUMBER_ID, CONTACT)
        self.exchanges: list[Exchange] = []
        self.tool_log: list[tuple[str, str]] = []
        channel.register(CONTACT)
        self.notes: list[str] = []

    # ------------------------------------------------------------ arranque

    @property
    def db(self) -> sqlite3.Connection:
        return self.app.state.db

    def set_reminder_minutes(self, minutes: int) -> None:
        """Lo mismo que mover el ajuste global en el panel."""
        self.app.state.runtime_settings.set_appointment_reminder_minutes(minutes, datetime.now(UTC))

    def set_followup_minutes(self, minutes: int) -> None:
        """El plazo del seguimiento **de reserva**: quien ya tenía un horario."""
        self.app.state.runtime_settings.set_booking_followup_minutes(minutes, datetime.now(UTC))

    def set_interest_followup_minutes(self, minutes: int) -> None:
        """El plazo del seguimiento **de interés**: quien no llegó a agendar.

        Es otro ajuste y otro slider en el panel, no el mismo con otro nombre. Un
        caso que quiera probar uno sin el otro tiene que poder moverlos por
        separado, que es justo la razón de que estén separados.
        """
        self.app.state.runtime_settings.set_interest_followup_minutes(minutes, datetime.now(UTC))

    # ------------------------------------------------------- conversación

    async def say(self, text: str, *, note: str | None = None) -> Exchange:
        """Un mensaje del paciente, por el webhook firmado, hasta que llega la respuesta."""
        mark = len(self.channel.sent)
        trace_mark = self._last_trace_id()
        evidencia_mark = len(self.tool_log)
        await self._post_kapso(text)
        replies = tuple(item.text for item in self.channel.since(mark))
        exchange = Exchange(
            text,
            replies,
            self._tools_since(trace_mark),
            evidencia=tuple(self.tool_log[evidencia_mark:]),
        )
        self.exchanges.append(exchange)
        if note:
            self.notes.append(note)
        return exchange

    async def burst(self, texts: Sequence[str]) -> Exchange:
        """Varios mensajes a la vez: lo que el debounce debe fundir en un turno."""
        mark = len(self.channel.sent)
        trace_mark = self._last_trace_id()
        evidencia_mark = len(self.tool_log)
        await asyncio.gather(*(self._post_kapso(text) for text in texts))
        replies = tuple(item.text for item in self.channel.since(mark))
        exchange = Exchange(
            " / ".join(texts),
            replies,
            self._tools_since(trace_mark),
            evidencia=tuple(self.tool_log[evidencia_mark:]),
        )
        self.exchanges.append(exchange)
        return exchange

    async def _post_kapso(self, text: str) -> None:
        body = json.dumps(
            {
                "message": {
                    "id": f"eval-{uuid.uuid4().hex[:12]}",
                    "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "type": "text",
                    "from": CONTACT,
                    "text": {"body": text},
                },
                "conversation": {"id": f"eval-{self.name}"},
                "phone_number_id": PHONE_NUMBER_ID,
            }
        ).encode()
        signature = hmac.new(KAPSO_SECRET.encode(), body, hashlib.sha256).hexdigest()
        response = await self.client.post(
            "/webhook/kapso",
            content=body,
            headers={"X-Webhook-Signature": signature, "Content-Type": "application/json"},
        )
        response.raise_for_status()

    # ----------------------------------------------------------- calendly

    def tokens(self) -> list[tuple[str, datetime]]:
        rows = self.db.execute(
            "SELECT token, slot_utc FROM booking_token"
            " WHERE phone_number_id = ? AND contact_phone = ? ORDER BY created_at DESC",
            (PHONE_NUMBER_ID, CONTACT),
        ).fetchall()
        return [(row["token"], _parse(row["slot_utc"])) for row in rows]

    async def book(
        self,
        *,
        token: str | None = None,
        slot: datetime | None = None,
        phone: str = CONTACT,
        name: str = "Paciente De Prueba",
        email: str = "paciente@example.test",
        event_uri: str | None = None,
    ) -> str:
        """`invitee.created`, tal cual lo manda Calendly cuando el paciente termina.

        El teléfono va en las respuestas del formulario porque el servicio lo
        exige: el enlace personalizado se puede reenviar, así que el número que
        recoge Calendly es lo que corrobora de quién es la reserva.
        """
        if token is None:
            issued = self.tokens()
            if not issued:
                raise AssertionError("no hay token de reserva: el bot nunca mandó el enlace")
            token, issued_slot = issued[0]
            slot = slot or issued_slot
        if slot is None:
            raise AssertionError("hace falta el horario de la reserva")
        uri = event_uri or f"https://api.calendly.com/scheduled_events/{uuid.uuid4()}"
        mark = len(self.channel.sent)
        await self._post_calendly(
            {
                "event": "invitee.created",
                "payload": {
                    "event": uri,
                    "name": name,
                    "email": email,
                    "tracking": {"utm_content": token},
                    "questions_and_answers": [{"question": "Número de teléfono", "answer": phone}],
                    "scheduled_event": {
                        "start_time": slot.astimezone(UTC).isoformat().replace("+00:00", "Z")
                    },
                },
            }
        )
        self.calendar.mark_booked(slot)
        self._record_system(mark, "calendly: reserva completada")
        return uri

    async def preparar_cita(self, *, en_minutos: int, max_turnos: int = 6) -> tuple[str, datetime]:
        """Precondición compartida: dejar una cita confirmada, con todo el flujo.

        No hay atajos: el hueco se ofrece en el calendario, el paciente lo pide, el
        bot negocia hasta mandar el enlace y sólo entonces se simula la reserva.
        Insertar la cita en la base saltándose `agendar_cita` probaría el webhook
        pero no la conversación, que es justo lo que hay que medir.

        Hacen falta varios turnos porque el bot confirma antes de mandar el enlace,
        y a veces propone otro horario. **La cita se hace sobre el horario del
        token, no sobre el que se pidió**: si el modelo ofrece otro hueco y el
        paciente acepta, forzar el horario original crearía una cita que no
        corresponde a ningún enlace emitido — una inconsistencia inventada por el
        arnés que luego parecería un bug del sistema.

        Devuelve `(event_uri, horario realmente reservado)`; los casos calculan sus
        tiempos a partir de ese horario.
        """
        objetivo = await self.calendar.elegir_hueco(en_minutos)
        await self.say(
            f"hola, quiero agendar la cita de valoración {self.frase_horario(objetivo)},"
            " ¿me pasas el enlace para reservarla?"
        )
        afirmaciones = [
            "sí, ese horario me sirve, mándame el enlace por favor",
            "sí, por favor, pásame el enlace de reserva",
            "sí, adelante, mándamelo",
        ]
        for intento in range(max_turnos):
            if self.tokens():
                break
            await self.say(afirmaciones[min(intento, len(afirmaciones) - 1)])
        emitidos = self.tokens()
        if not emitidos:
            raise AssertionError(
                f"el bot no mandó el enlace de reserva en {max_turnos} turnos:"
                " no se puede montar la precondición del caso.\n"
                f"conversación:\n{self.transcript()}"
            )
        token, slot = emitidos[0]
        uri = await self.book(token=token, slot=slot)
        return uri, slot

    def frase_horario(self, slot_utc: datetime) -> str:
        """Cómo pide un paciente un horario concreto: **con las mismas palabras
        que usa el bot para ofrecerlo**.

        Usa `slot_label`, que es exactamente la función con la que `ver_horarios`
        etiqueta cada hueco. Eso no es elegancia, es lo único que funciona: si el
        arnés dice "el 22/08 a las 20:21" y el bot ha listado ese mismo hueco como
        "hoy, 8:21 p. m.", el modelo no reconoce su propio horario y la
        conversación se va en aclarar fechas. Se probaron las dos formas y cada
        una rompía un caso distinto; la etiqueta compartida no rompe ninguno,
        porque no hay dos vocabularios que reconciliar.
        """
        zona = ZoneInfo(self.settings.calendly_timezone)
        return slot_label(Slot(slot_utc, slot_utc), zona, datetime.now(UTC))

    async def preparar_cita_directa(self, *, en_minutos: int, max_turnos: int = 6) -> Reserva:
        """Precondición de los casos que esperan que el bot reserve él mismo.

        Igual que `preparar_cita`, pero sin dar por hecho el enlace: tras cada
        turno mira si ya hay cita en la base. Si la hay, la reservó el sistema y
        eso es lo que estos casos quieren medir.

        Si el sistema no reserva pero sí emite un token, **no revienta**: cae al
        flujo de enlace, monta la cita igual y lo marca en `por_el_sistema`. Esa
        tolerancia es deliberada. Mientras `agendar_cita` siga mandando enlaces,
        estos casos tienen que poder ejecutarse y medir todo lo demás — qué dice
        el bot, si duplica citas, si avisa — en vez de morir todos con el mismo
        error de precondición y no enseñar nada.
        """
        objetivo = await self.calendar.elegir_hueco(en_minutos)
        await self.say(
            f"hola, quiero agendar la cita de valoración {self.frase_horario(objetivo)}, por favor"
        )
        afirmaciones = [
            "sí, ese horario me sirve, agéndamelo",
            "sí, por favor, resérvamelo",
            "sí, adelante",
        ]
        for intento in range(max_turnos):
            reservada = self._cita_vigente()
            if reservada is not None:
                return Reserva(reservada.event_uri, reservada.slot_utc, True)
            if self.tokens():
                break
            await self.say(afirmaciones[min(intento, len(afirmaciones) - 1)])

        reservada = self._cita_vigente()
        if reservada is not None:
            return Reserva(reservada.event_uri, reservada.slot_utc, True)

        emitidos = self.tokens()
        if not emitidos:
            raise AssertionError(
                f"el bot ni reservó ni mandó enlace en {max_turnos} turnos:"
                " no se puede montar la precondición del caso.\n"
                f"conversación:\n{self.transcript()}"
            )
        token, slot = emitidos[0]
        uri = await self.book(token=token, slot=slot)
        return Reserva(uri, slot, False)

    def _cita_vigente(self) -> Appointment | None:
        vigentes = self.state().scheduled
        return vigentes[0] if vigentes else None

    async def cancel(self, event_uri: str | None = None) -> None:
        """`invitee.canceled`: el único camino que hoy libera un hueco."""
        uri = event_uri or self._latest_event_uri()
        if uri is None:
            raise AssertionError("no hay cita que cancelar")
        slot = next(
            (item.slot_utc for item in self.state().appointments if item.event_uri == uri), None
        )
        mark = len(self.channel.sent)
        await self._post_calendly({"event": "invitee.canceled", "payload": {"event": uri}})
        if slot is not None:
            self.calendar.mark_free(slot)
        self._record_system(mark, "calendly: cancelación")

    async def _post_calendly(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        stamp = str(int(datetime.now(UTC).timestamp()))
        digest = hmac.new(
            CALENDLY_SIGNING_KEY.encode(), f"{stamp}.".encode() + body, hashlib.sha256
        ).hexdigest()
        response = await self.client.post(
            "/webhook/calendly",
            content=body,
            headers={
                "Calendly-Webhook-Signature": f"t={stamp},v1={digest}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()

    # -------------------------------------------------------------- panel

    async def panel_login(self) -> None:
        """La sesión del panel, por su propia ruta: la cookie la guarda el cliente."""
        response = await self.client.post(
            "/admin/api/login", json={"password": self.settings.panel_password}
        )
        response.raise_for_status()

    async def panel(self, path: str, **body: Any) -> dict[str, Any]:
        """Una acción del panel tal como la manda el SPA, con guardia de sesión incluida."""
        if not self.client.cookies.get("agente_panel"):
            await self.panel_login()
        response = await self.client.post(f"/admin/api/{path.lstrip('/')}", json=body)
        response.raise_for_status()
        return response.json()

    async def panel_mute(self, muted: bool, *, expires_in: int | None = None) -> dict[str, Any]:
        return await self.panel(
            "mute",
            phone_number_id=PHONE_NUMBER_ID,
            contact_phone=CONTACT,
            muted=muted,
            expires_in=expires_in,
        )

    async def set_interest_followup_enabled(self, enabled: bool) -> None:
        """El interruptor del seguimiento tras el silencio, por la ruta del panel.

        Por HTTP y no tocando `runtime_settings` a mano, al revés que los
        sliders, porque aquí el interruptor hace dos cosas: guarda el ajuste y
        vacía lo que ya estaba en cola. Un caso que sólo escribiera el ajuste
        probaría media conducta y daría por bueno un apagado que deja avisos
        vivos esperando a que alguien vuelva a encenderlo.
        """
        await self.panel("interest-followup-enabled", enabled=enabled)

    async def set_reminder_enabled(self, enabled: bool) -> None:
        """El interruptor del recordatorio previo a la cita, por la ruta del panel.

        Separado del anterior a propósito: apagar los recordatorios no apaga el
        seguimiento, ni al revés. Encenderlo sí reconstruye la cola, porque las
        citas siguen ahí.
        """
        await self.panel("appointment-reminder-enabled", enabled=enabled)

    async def panel_state(self) -> dict[str, Any]:
        if not self.client.cookies.get("agente_panel"):
            await self.panel_login()
        response = await self.client.get("/admin/api/state")
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------ tiempo

    async def fire_due(self, at: datetime | None = None) -> tuple[str, ...]:
        """Adelantar el reloj **de lo que vence**, sin tocar el reloj del proceso."""
        moment = at or datetime.now(UTC)
        mark = len(self.channel.sent)
        await self.app.state.booking_followups.send_due(moment)
        await self.app.state.interest_followups.send_due(moment)
        await self.app.state.appointment_reminders.send_due(moment)
        salidas = tuple(item.text for item in self.channel.since(mark))
        self._record_system(mark, f"vencimientos disparados a {moment.isoformat()}")
        return salidas

    async def force_reminder(self) -> str:
        """El botón "forzar recordatorio" del panel, por el mismo camino que el panel."""
        mark = len(self.channel.sent)
        result = await self.app.state.appointment_reminders.send_now(self.key)
        self._record_system(mark, f"panel: forzar recordatorio -> {result}")
        return result

    async def force_interest_followup(self) -> str:
        """El botón "enviar seguimiento ahora" del panel, para quien no tiene cita.

        Gemelo de `force_reminder` y deliberadamente distinto: aquél manda el
        recordatorio de una cita que existe, éste retoma a alguien que nunca llegó
        a tenerla. En el panel son dos botones que ni siquiera pueden aparecer a
        la vez, porque uno pide cita y el otro pide que no la haya.
        """
        mark = len(self.channel.sent)
        result = await self.app.state.interest_followups.send_now(self.key)
        self._record_system(mark, f"panel: forzar seguimiento de interés -> {result}")
        return result

    def ocupacion(self, slot_utc: datetime) -> bool | None:
        """¿El hueco sigue bloqueado? `None` cuando el modo no puede responderlo.

        En modo real la reserva se simula por webhook y el hueco nunca llega a
        ocuparse en Calendly. Devolver `False` ahí sería mentir: el criterio se
        registra como informativo y no cuenta ni como acierto ni como fallo.
        """
        if not getattr(self.calendar, "soporta_ocupacion", False):
            return None
        return self.calendar.is_booked(slot_utc)

    # ------------------------------------------------------------- estado

    def state(self) -> Snapshot:
        appointments = SqliteAppointmentsRepository(self.db).for_contact(self.key)
        rows = self.db.execute(
            "SELECT kind, due_at, sent_at, text, appointment_event_id FROM outbox"
            " WHERE phone_number_id = ? AND contact_phone = ? ORDER BY id",
            (PHONE_NUMBER_ID, CONTACT),
        ).fetchall()
        profile = SqliteContactsRepository(self.db).get_profile(self.key)
        return Snapshot(
            appointments=tuple(
                Appointment(item.slot_utc, item.status, item.calendly_event_id)
                for item in appointments
            ),
            outbox=tuple(
                Pending(
                    row["kind"],
                    _parse(row["due_at"]),
                    _parse(row["sent_at"]) if row["sent_at"] else None,
                    row["text"],
                    row["appointment_event_id"],
                )
                for row in rows
            ),
            muted=SqliteMutesRepository(self.db).is_bot_muted(self.key, datetime.now(UTC)),
            mute_reason=_mute_reason(self.db, self.key),
            profile=_profile(profile),
            tokens=tuple(token for token, _ in self.tokens()),
        )

    def transcript(self) -> str:
        lines: list[str] = []
        for item in self.exchanges:
            prefix = "→" if item.origin == "paciente" else "·"
            lines.append(f"{prefix} {item.sent}")
            for reply in item.replies:
                lines.append(f"← {reply}")
            if item.tools:
                lines.append(f"  [herramientas: {', '.join(item.tools)}]")
            for nombre, salida in item.evidencia:
                resumen = " ".join(salida.split())
                lines.append(
                    f"  [{nombre} devolvió: {resumen[:300]}{'…' if len(resumen) > 300 else ''}]"
                )
        return "\n".join(lines)

    # ------------------------------------------------------------ interno

    def _record_system(self, mark: int, label: str) -> None:
        replies = tuple(item.text for item in self.channel.since(mark))
        self.exchanges.append(Exchange(label, replies, origin="sistema"))

    def _latest_event_uri(self) -> str | None:
        scheduled = self.state().scheduled
        return scheduled[-1].event_uri if scheduled else None

    def _last_trace_id(self) -> int:
        row = self.db.execute("SELECT COALESCE(MAX(id), 0) AS id FROM llm_trace").fetchone()
        return int(row["id"])

    def _tools_since(self, trace_id: int) -> tuple[str, ...]:
        rows = self.db.execute(
            "SELECT tools_called FROM llm_trace WHERE id > ? ORDER BY id", (trace_id,)
        ).fetchall()
        used: list[str] = []
        for row in rows:
            for name in json.loads(row["tools_called"] or "[]"):
                if name not in used:
                    used.append(name)
        return tuple(used)


def _profile(profile: Any) -> dict[str, Any] | None:
    if profile is None:
        return None
    return {
        "nombre": profile.name,
        "correo": profile.email,
        "tipo": profile.kind,
        "citas": profile.appointment_count,
        "proxima_cita": profile.next_appointment_utc,
        "handoff": profile.handoff_state,
    }


def _mute_reason(conn: sqlite3.Connection, key: ContactKey) -> str | None:
    row = conn.execute(
        "SELECT reason FROM audit_log WHERE contact_phone = ? ORDER BY id DESC LIMIT 1",
        (key.contact_phone,),
    ).fetchone()
    return row["reason"] if row else None


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


@asynccontextmanager
async def world(name: str, *, calendario: str | None = None, **overrides: Any):
    """Arranca la app con los dobles puestos y la apaga al salir.

    Los dobles se inyectan sustituyendo las clases **en el módulo de composición**
    antes de construir la app: así el cableado que se ejecuta es el de producción,
    línea por línea, y no una versión de test del mismo cableado.
    """
    run_dir = RUNS_DIR / name
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "agente.db"
    if db_path.exists():
        db_path.unlink()

    modo = modo_configurado(calendario)
    base = load_settings()
    ajustes: dict[str, Any] = {
        "db_path": db_path,
        # Kapso nunca es real: la clave se sustituye por una inerte para que un
        # error de cableado no pueda acabar en un envío.
        "kapso_webhook_secret": KAPSO_SECRET,
        "kapso_phone_number_id": PHONE_NUMBER_ID,
        "kapso_api_key": "eval-unused",
        # La firma de Calendly es siempre la nuestra: el webhook lo emite el
        # arnés, incluso cuando la disponibilidad viene de Calendly de verdad.
        "calendly_signing_key": CALENDLY_SIGNING_KEY,
        # Que nada venza solo: los vencimientos los dispara el test.
        "booking_followup_poll_seconds": 3600.0,
        # El seguimiento de interés se arma en cuanto el bot le responde a alguien
        # sin cita, o sea en casi todos los casos. Arrancarlo en el máximo lo deja
        # programado pero fuera del alcance de cualquier `fire_due` razonable, así
        # que sólo aparece donde un caso lo baja a propósito (C01). Sin esto, un
        # caso que adelanta vencimientos para ver su recordatorio se llevaría de
        # propina un "¿sigues por ahí?" que nadie pidió medir.
        "interest_followup_minutes": 90,
        # El correo con el que se reserva. Fijo aquí y no leído de `.env` para
        # que un caso no dependa de cómo tenga configurada su clínica quien lo
        # ejecute; el doble lo ignora y Calendly real sólo lo necesita presente.
        "calendly_invitee_email": "evals@example.com",
    }
    if modo == "fake":
        ajustes["calendly_token"] = "eval-unused"
    settings = base.model_copy(update=ajustes | overrides)
    channel = RecordingChannel()
    calendar = crear_calendario(modo, settings)
    tool_log: list[tuple[str, str]] = []
    build_tools_real = app_module.build_tools

    def build_tools_observado(**kwargs: Any):
        """Las mismas herramientas, anotando qué devolvió cada una.

        Es un observador, no un doble: llama al registro real y deja pasar el
        resultado intacto. Existe porque el juez necesita ver la evidencia que
        tuvo el modelo — de otro modo lee un precio correcto recuperado de la
        wiki y un precio inventado como si fueran la misma frase.
        """
        definiciones, handlers = build_tools_real(**kwargs)

        def observar(nombre: str, handler):
            async def envuelto(data: dict[str, Any]) -> str:
                salida = await handler(data)
                tool_log.append((nombre, salida))
                return salida

            return envuelto

        return definiciones, {n: observar(n, h) for n, h in handlers.items()}

    with (
        patch.object(app_module, "KapsoClient", lambda *a, **k: channel),
        patch.object(app_module, "CalendlyClient", lambda *a, **k: calendar),
        patch.object(app_module, "build_tools", build_tools_observado),
    ):
        app = app_module.create_app(settings)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://eval", timeout=180
            ) as client:
                mundo = World(name, app, client, channel, calendar, settings, modo)
                mundo.tool_log = tool_log
                yield mundo
