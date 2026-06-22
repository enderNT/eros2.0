"""Tests del cliente Chatwoot (enviar mensaje, set atributo). Sin red."""

import httpx

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
