"""Tests de los agentes FAQ y Conversación (T6, T7 · V4)."""

import agente.nodes.agentes as A


def _state(text="¿cuánto cuesta?"):
    return {"messages": [{"role": "user", "content": text}], "perfil": {}, "tarea": {}, "meta": {}}


def test_faq_v4_prompt_incluye_wiki_y_abstencion(monkeypatch):
    captura = {}

    def fake_generar(system, messages, model, **k):
        captura["system"] = system
        return "respuesta"

    monkeypatch.setattr(A, "generar", fake_generar)
    monkeypatch.setattr(A, "cargar_wiki", lambda: "PRECIO: 500 MXN")
    out = A.agente_faq(_state())

    blob = " ".join(b["text"] for b in captura["system"])
    assert "PRECIO: 500 MXN" in blob  # responde desde la Wiki
    assert "ÚNICAMENTE" in blob and "inventes" in blob.lower()  # abstención
    assert out["salida"]["resultado"] == "resuelto"


def test_faq_fallback_sin_key(monkeypatch):
    monkeypatch.setattr(A, "generar", lambda *a, **k: None)
    monkeypatch.setattr(A, "cargar_wiki", lambda: "x")
    out = A.agente_faq(_state())
    assert out["salida"]["resultado"] == "resuelto"
    assert out["salida"]["texto"]


def test_conversacion_resuelve(monkeypatch):
    monkeypatch.setattr(A, "generar", lambda *a, **k: "¡hola!")
    out = A.agente_conversacion(_state("hola"))
    assert out["salida"] == {"texto": "¡hola!", "resultado": "resuelto"}
