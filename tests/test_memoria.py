"""Tests de memoria larga: store, ensamblar_contexto, persistir (T9, T10, T11 · V5, V6)."""

import agente.nodes.contexto as Ctx
import agente.nodes.egress as Eg
from agente.store import Store


def test_store_registrar_y_get():
    s = Store(":memory:")
    assert s.get_perfil("u1")["memoria_larga"]["citas_previas"] == 0
    s.registrar_cita("u1", "2026-07-01T18:00:00Z")
    s.registrar_cita("u1", "2026-07-08T18:00:00Z")
    p = s.get_perfil("u1")
    assert p["memoria_larga"]["citas_previas"] == 2
    assert p["memoria_larga"]["ultima_cita"] == "2026-07-08T18:00:00Z"


def test_store_v5_solo_admin():
    p = Store(":memory:").get_perfil("u")
    assert set(p.keys()) == {"identidad", "memoria_larga"}
    assert set(p["memoria_larga"].keys()) == {"citas_previas", "ultima_cita"}


def test_v6_ensamblar_hidrata_fresco(monkeypatch):
    class FakeStore:
        def get_perfil(self, uid):
            return {"identidad": {"nombre": "Ana"}, "memoria_larga": {"citas_previas": 3, "ultima_cita": "x"}}

    monkeypatch.setattr(Ctx, "get_store", lambda: FakeStore())
    out = Ctx.ensamblar_contexto({"meta": {"user_id": "u1"}})
    assert out["perfil"]["memoria_larga"]["citas_previas"] == 3


def test_v5_persistir_solo_en_confirmada(monkeypatch):
    llamadas = []

    class FakeStore:
        def registrar_cita(self, uid, fecha):
            llamadas.append((uid, fecha))

    monkeypatch.setattr(Eg, "get_store", lambda: FakeStore())

    Eg.persistir({"tarea": {"subestado": "RECOPILANDO"}, "meta": {"user_id": "u1"}})
    assert llamadas == []

    Eg.persistir(
        {"tarea": {"subestado": "CONFIRMADA", "slot_elegido": "2026-07-01T18:00:00Z"}, "meta": {"user_id": "u1"}}
    )
    assert llamadas == [("u1", "2026-07-01T18:00:00Z")]
