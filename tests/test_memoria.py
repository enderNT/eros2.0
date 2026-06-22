"""Tests del store Postgres: perfil, historial y resumen."""

import os
import uuid

import pytest

from agente.store import Store


def _store():
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("Postgres no configurado para tests de memoria")
    return Store(url)


def test_store_registrar_y_get():
    s = _store()
    user_id = f"u-{uuid.uuid4().hex}"
    assert s.get_perfil(user_id)["memoria_larga"]["citas_previas"] == 0
    s.registrar_cita(user_id, "2026-07-01T18:00:00Z")
    s.registrar_cita(user_id, "2026-07-08T18:00:00Z")
    p = s.get_perfil(user_id)
    assert p["memoria_larga"]["citas_previas"] == 2
    assert p["memoria_larga"]["ultima_cita"] == "2026-07-08T18:00:00Z"


def test_store_solo_campos_admin():
    p = _store().get_perfil(f"u-{uuid.uuid4().hex}")
    assert set(p.keys()) == {"identidad", "memoria_larga"}
    assert set(p["memoria_larga"].keys()) == {"citas_previas", "ultima_cita"}


def test_historial_orden_cronologico():
    s = _store()
    conv = f"c-{uuid.uuid4().hex}"
    s.agregar_turno(conv, "user", "hola", "u1")
    s.agregar_turno(conv, "assistant", "¡hola! ¿en qué te ayudo?", "u1")
    s.agregar_turno(conv, "user", "quiero una cita", "u1")
    h = s.cargar_historial(conv)
    assert [m["role"] for m in h] == ["user", "assistant", "user"]
    assert h[0]["content"] == "hola"
    assert h[-1]["content"] == "quiero una cita"


def test_historial_ventana_limita_y_separa_conversaciones():
    s = _store()
    conv = f"c-{uuid.uuid4().hex}"
    other = f"c-{uuid.uuid4().hex}"
    for i in range(5):
        s.agregar_turno(conv, "user", f"m{i}", "u1")
    s.agregar_turno(other, "user", "otra conversación", "u1")
    ult = s.cargar_historial(conv, limite=2)
    assert [m["content"] for m in ult] == ["m3", "m4"]
    assert s.cargar_historial(other) == [{"role": "user", "content": "otra conversación"}]


def test_resumen_rodante():
    s = _store()
    conv = f"c-{uuid.uuid4().hex}"
    assert s.get_resumen(conv) == ""
    s.set_resumen(conv, "Se discutió valoración.", "u1")
    assert s.get_resumen(conv) == "Se discutió valoración."
