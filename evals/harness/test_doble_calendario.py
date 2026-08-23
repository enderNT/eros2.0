"""El doble de calendario contra las reglas reales de Calendly.

Un doble sólo sirve si miente poco. Estas pruebas fijan las reglas de escritura
que se verificaron contra la API real el 2026-08-22 — `already_filled`, la
liberación del hueco al cancelar, la cancelación repetida — para que el día que
un caso se apoye en ellas no se esté apoyando en una suposición.

    .venv-evals/bin/python -m pytest evals/harness/test_doble_calendario.py -q
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agente.domain.errors import CalendlyError, SlotTakenError

from .fakes import FakeCalendar

RESERVA = {
    "name": "Ana",
    "email": "ana@example.com",
    "timezone": "America/Mexico_City",
    "phone": "+525599998888",
}


@pytest.fixture()
def calendario() -> FakeCalendar:
    return FakeCalendar()


async def _un_hueco(calendario: FakeCalendar):
    inicio = datetime.now(UTC) + timedelta(days=1)
    return calendario.add_slot(inicio.replace(microsecond=0))


async def test_reservar_ocupa_el_hueco_y_lo_retira_de_disponibilidad(calendario) -> None:
    hueco = await _un_hueco(calendario)
    reserva = await calendario.book(hueco, **RESERVA)
    assert reserva.start_utc == hueco.start_utc
    assert calendario.is_booked(hueco.start_utc)
    ofrecidos = await calendario.availability(
        datetime.now(UTC), datetime.now(UTC) + timedelta(days=3)
    )
    assert hueco.start_utc not in [s.start_utc for s in ofrecidos]


async def test_reservar_dos_veces_el_mismo_hueco_es_imposible(calendario) -> None:
    """C09 muere aquí: Calendly arbitra, así que la doble reserva no existe."""
    hueco = await _un_hueco(calendario)
    await calendario.book(hueco, **RESERVA)
    with pytest.raises(SlotTakenError):
        await calendario.book(hueco, **RESERVA)


async def test_cancelar_libera_el_hueco_en_el_acto(calendario) -> None:
    """La mitad que hace posible reagendar sin endpoint de reagendado."""
    hueco = await _un_hueco(calendario)
    reserva = await calendario.book(hueco, **RESERVA)
    await calendario.cancel(reserva.event_id)
    assert not calendario.is_booked(hueco.start_utc)
    ofrecidos = await calendario.availability(
        datetime.now(UTC), datetime.now(UTC) + timedelta(days=3)
    )
    assert hueco.start_utc in [s.start_utc for s in ofrecidos]


async def test_reagendar_es_cancelar_y_volver_a_reservar(calendario) -> None:
    viejo = await _un_hueco(calendario)
    nuevo = calendario.add_slot((datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0))
    primera = await calendario.book(viejo, **RESERVA)
    await calendario.cancel(primera.event_id, reason="el paciente movió la cita")
    segunda = await calendario.book(nuevo, **RESERVA)
    assert not calendario.is_booked(viejo.start_utc)
    assert calendario.is_booked(nuevo.start_utc)
    assert segunda.event_id != primera.event_id


async def test_el_hueco_liberado_se_puede_volver_a_reservar_con_id_nuevo(calendario) -> None:
    """Un id repetido chocaría con el índice único de `calendly_event_id`."""
    hueco = await _un_hueco(calendario)
    primera = await calendario.book(hueco, **RESERVA)
    await calendario.cancel(primera.event_id)
    segunda = await calendario.book(hueco, **RESERVA)
    assert segunda.event_id != primera.event_id


async def test_cancelar_dos_veces_no_falla(calendario) -> None:
    hueco = await _un_hueco(calendario)
    reserva = await calendario.book(hueco, **RESERVA)
    await calendario.cancel(reserva.event_id)
    await calendario.cancel(reserva.event_id)


async def test_cancelar_algo_desconocido_si_falla(calendario) -> None:
    with pytest.raises(CalendlyError):
        await calendario.cancel("https://calendly.test/scheduled_events/9999")


async def test_una_cita_cancelada_no_reaparece_como_reservada(calendario) -> None:
    hueco = await _un_hueco(calendario)
    reserva = await calendario.book(hueco, **RESERVA)
    await calendario.cancel(reserva.event_id)
    otra = await calendario.book(hueco, **RESERVA)
    await calendario.cancel(reserva.event_id)
    assert calendario.is_booked(hueco.start_utc), "cancelar la vieja no debe soltar la nueva"
    assert otra.event_id in calendario.bookings
