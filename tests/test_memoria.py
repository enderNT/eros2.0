"""Tests del store: perfil (memoria larga) e historial (memoria corta)."""

from agente.store import Store


def test_store_registrar_y_get():
    s = Store(":memory:")
    assert s.get_perfil("u1")["memoria_larga"]["citas_previas"] == 0
    s.registrar_cita("u1", "2026-07-01T18:00:00Z")
    s.registrar_cita("u1", "2026-07-08T18:00:00Z")
    p = s.get_perfil("u1")
    assert p["memoria_larga"]["citas_previas"] == 2
    assert p["memoria_larga"]["ultima_cita"] == "2026-07-08T18:00:00Z"


def test_store_solo_campos_admin():
    p = Store(":memory:").get_perfil("u")
    assert set(p.keys()) == {"identidad", "memoria_larga"}
    assert set(p["memoria_larga"].keys()) == {"citas_previas", "ultima_cita"}


def test_historial_orden_cronologico():
    s = Store(":memory:")
    s.agregar_turno("c1", "user", "hola")
    s.agregar_turno("c1", "assistant", "¡hola! ¿en qué te ayudo?")
    s.agregar_turno("c1", "user", "quiero una cita")
    h = s.cargar_historial("c1")
    assert [m["role"] for m in h] == ["user", "assistant", "user"]
    assert h[0]["content"] == "hola"
    assert h[-1]["content"] == "quiero una cita"


def test_historial_ventana_limita_y_separa_conversaciones():
    s = Store(":memory:")
    for i in range(5):
        s.agregar_turno("c1", "user", f"m{i}")
    s.agregar_turno("c2", "user", "otra conversación")
    ult = s.cargar_historial("c1", limite=2)
    assert [m["content"] for m in ult] == ["m3", "m4"]
    assert s.cargar_historial("c2") == [{"role": "user", "content": "otra conversación"}]
