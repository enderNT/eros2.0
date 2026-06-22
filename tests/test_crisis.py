"""Tests del chequeo de crisis (T2 · V2)."""

import agente.nodes.gates as G
from agente.llm import ChequeoCrisis


def _state(text):
    return {"messages": [{"role": "user", "content": text}], "meta": {}}


def test_v2_crisis_detectada_setea_handoff(monkeypatch):
    monkeypatch.setattr(
        G, "detectar_crisis", lambda s, c: ChequeoCrisis(crisis=True, motivo="riesgo")
    )
    out = G.chequeo_crisis(_state("ya no quiero seguir aquí"))
    assert out["meta"]["crisis"] is True
    assert out["meta"]["handoff_reason"] == "crisis"
    assert "salida" in out and out["salida"]["texto"] == G.settings.crisis_message


def test_v2_sin_crisis_no_escala(monkeypatch):
    monkeypatch.setattr(
        G, "detectar_crisis", lambda s, c: ChequeoCrisis(crisis=False, motivo="-")
    )
    out = G.chequeo_crisis(_state("hola, buenas tardes"))
    assert out["meta"]["crisis"] is False
    assert "salida" not in out


def test_v2_fallback_keywords(monkeypatch):
    # Sin API key (detectar_crisis -> None): red de seguridad por palabras clave.
    monkeypatch.setattr(G, "detectar_crisis", lambda s, c: None)
    assert G.chequeo_crisis(_state("estoy pensando en suicidarme"))["meta"]["crisis"] is True
    assert G.chequeo_crisis(_state("¿cuánto cuesta?"))["meta"]["crisis"] is False
