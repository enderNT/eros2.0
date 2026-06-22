"""Tests de Chatwoot: cliente, enviar, handoff (T12, T13 · V7). Sin red."""

import httpx

import agente.nodes.egress as Eg
from agente.chatwoot import ChatwootClient


def _cw(handler):
    transport = httpx.MockTransport(handler)
    http = httpx.Client(base_url="https://cw.example.com", transport=transport)
    return ChatwootClient("https://cw.example.com", "tok", "1", http=http)


def test_enviar_mensaje_outgoing():
    cap = {}

    def h(req):
        cap["url"] = str(req.url)
        cap["body"] = req.content.decode()
        return httpx.Response(200, json={"id": 1})

    _cw(h).enviar_mensaje(42, "hola")
    assert "/conversations/42/messages" in cap["url"]
    assert "outgoing" in cap["body"] and "hola" in cap["body"]


def test_set_atributo():
    cap = {}

    def h(req):
        cap["url"] = str(req.url)
        cap["body"] = req.content.decode()
        return httpx.Response(200, json={})

    _cw(h).set_atributo(42, "bot_activo", False)
    assert "/conversations/42/custom_attributes" in cap["url"]
    assert "bot_activo" in cap["body"]


def test_v7_handoff_apaga_bot(monkeypatch):
    acciones = []

    class FakeCW:
        def enviar_mensaje(self, c, t):
            acciones.append(("msg", c, t))

        def set_atributo(self, c, k, v):
            acciones.append(("attr", c, k, v))

    monkeypatch.setattr(Eg, "get_chatwoot", lambda: FakeCW())
    out = Eg.handoff({"meta": {"conversation_id": 42, "handoff_reason": "cortesia"}, "salida": {}})
    assert ("attr", 42, "bot_activo", False) in acciones
    assert out["meta"]["bot_activo"] is False


def test_enviar_node_local_sin_cw(monkeypatch):
    monkeypatch.setattr(Eg, "get_chatwoot", lambda: None)
    assert Eg.enviar({"salida": {"texto": "x"}, "meta": {}}) == {}
