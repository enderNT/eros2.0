"""El interruptor del calendario: doble determinista o Calendly de verdad.

La idea de fondo del arnés es que se pueda **elegir cuánto sistema real entra en
la prueba**, en vez de decidirlo una vez para siempre. Kapso no es negociable:
mandar WhatsApp reales para leer una respuesta no es una prueba, es un envío.
Calendly sí lo es, y las dos posiciones responden preguntas distintas:

* `fake` — la cuadrícula es fija y el hueco se inyecta donde haga falta. Sirve
  para medir **comportamiento**: qué dice el bot, qué herramienta usa, qué queda
  en la base. Repetible, gratis y sin depender de la agenda de esta semana.
* `real` — la disponibilidad, las URL por hueco y las etiquetas horarias salen
  de la API de Calendly. Sirve para medir **integración**: que sigamos leyendo
  bien lo que Calendly devuelve hoy, no lo que devolvía cuando se escribió el
  adaptador.

Hoy, en `real` **no se escribe nada en Calendly**. Las herramientas del agente
sólo leen disponibilidad y copian la `scheduling_url` que ya viene en cada hueco;
la reserva se sigue simulando con un `invitee.created` firmado contra nuestro
propio webhook.

Eso tiene una consecuencia que hay que decir en voz alta: mientras siga así, en
`real` **el hueco nunca se ocupa de verdad**. Por eso existe `soporta_ocupacion`:
los criterios que preguntan "¿el hueco siguió bloqueado?" no pueden responderse
en modo real y se registran como informativos en vez de dar un falso `NO`.

Los dos adaptadores ya exponen `book` y `cancel`, que sí escriben. Nadie los
llama todavía — engancharlos es lo que convertirá `soporta_ocupacion` en cierto
para el modo real, y ese día habrá que apuntar los casos a un calendario de
pruebas, porque cada ejecución dejará citas de verdad en la agenda.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Literal

from agente.adapters.calendly.client import CalendlyClient
from agente.config import Settings
from agente.domain.errors import CalendlyError
from agente.ports.calendar import Booking, CalendarSlot

from .fakes import FakeCalendar

Modo = Literal["fake", "real"]
VARIABLE = "EVAL_CALENDARIO"
MODO_POR_DEFECTO: Modo = "fake"


def modo_configurado(explicito: str | None = None) -> Modo:
    """`fake` salvo que alguien pida `real` a propósito.

    El defecto es el modo que no toca nada de fuera: una prueba no debería
    llamar a un servicio externo porque a nadie se le ocurrió decir que no.
    """
    valor = (explicito or os.environ.get(VARIABLE) or MODO_POR_DEFECTO).strip().lower()
    if valor not in ("fake", "real"):
        raise ValueError(f"{VARIABLE} debe ser 'fake' o 'real', no {valor!r}")
    return valor  # type: ignore[return-value]


class CalendlyEnVivo:
    """Adaptador real de Calendly con la interfaz que el arnés necesita.

    Delega en el `CalendlyClient` de producción — el mismo objeto que usaría la
    app desplegada — y añade sólo lo que un caso necesita para orquestarse:
    elegir un hueco existente y decir con honestidad qué puede y qué no puede
    afirmar sobre él.
    """

    soporta_ocupacion = False
    soporta_inyectar_hueco = False

    def __init__(self, cliente: CalendlyClient, *, dias: int = 14) -> None:
        self._cliente, self._dias = cliente, dias

    async def availability(self, start: datetime, end: datetime) -> list[CalendarSlot]:
        return await self._cliente.availability(start, end)

    async def book(
        self,
        slot: CalendarSlot,
        *,
        name: str,
        email: str,
        timezone: str,
        phone: str,
    ) -> Booking:
        return await self._cliente.book(
            slot, name=name, email=email, timezone=timezone, phone=phone
        )

    async def cancel(self, event_id: str, *, reason: str = "") -> None:
        await self._cliente.cancel(event_id, reason=reason)

    async def create_invitee(self, slot: CalendarSlot, name: str, email: str) -> str:
        return await self._cliente.create_invitee(slot, name, email)

    async def aclose(self) -> None:
        await self._cliente.aclose()

    async def elegir_hueco(self, en_minutos: int) -> datetime:
        """El hueco real más cercano al momento pedido.

        No se puede inventar un hueco en la agenda de la clínica, así que el caso
        se adapta a lo que hay. Los tiempos de cada caso se calculan a partir del
        horario devuelto, no del pedido, justo para que esto no rompa nada.
        """
        ahora = datetime.now(UTC)
        deseado = ahora + timedelta(minutes=en_minutos)
        try:
            huecos = await self.availability(ahora, ahora + timedelta(days=self._dias))
        except CalendlyError as exc:
            raise AssertionError(
                "Calendly no respondió a la consulta de disponibilidad."
                " Revisa CALENDLY_TOKEN y CALENDLY_EVENT_TYPE_URI en .env,"
                f" o ejecuta el caso en modo fake. Detalle: {exc}"
            ) from exc
        if not huecos:
            raise AssertionError(
                "Calendly no ofrece ningún hueco en los próximos"
                f" {self._dias} días: este caso no se puede montar en modo real."
            )
        return min(huecos, key=lambda h: abs((h.start_utc - deseado).total_seconds())).start_utc

    # Lo que en modo real no se puede afirmar, se dice en vez de fingirse.

    def add_slot(self, start_utc: datetime) -> CalendarSlot:
        raise AssertionError(
            "no se pueden inyectar huecos en la agenda real:"
            " usa `elegir_hueco` o ejecuta el caso en modo fake"
        )

    def mark_booked(self, start_utc: datetime) -> None:
        return None

    def mark_free(self, start_utc: datetime) -> None:
        return None

    def is_booked(self, start_utc: datetime) -> bool:
        raise AssertionError(
            "en modo real la reserva se simula por webhook y el hueco sigue libre"
            " en Calendly: consulta `soporta_ocupacion` antes de preguntar"
        )


class CalendarioFalso(FakeCalendar):
    """El doble determinista, con la misma interfaz de orquestación."""

    soporta_ocupacion = True
    soporta_inyectar_hueco = True

    async def elegir_hueco(self, en_minutos: int) -> datetime:
        objetivo = (datetime.now(UTC) + timedelta(minutes=en_minutos)).replace(
            second=0, microsecond=0
        )
        self.add_slot(objetivo)
        return objetivo


def crear_calendario(modo: Modo, settings: Settings) -> CalendarioFalso | CalendlyEnVivo:
    if modo == "fake":
        return CalendarioFalso(timezone=settings.calendly_timezone)
    if not settings.calendly_token or not settings.calendly_event_type_uri:
        raise AssertionError(
            "modo real sin credenciales: define CALENDLY_TOKEN y"
            " CALENDLY_EVENT_TYPE_URI en .env, o ejecuta en modo fake"
        )
    return CalendlyEnVivo(CalendlyClient(settings.calendly_token, settings.calendly_event_type_uri))
