"""Tests del Supervisor (T1). Cubren V8 (salida estructurada) y V11 (sticky)."""

from agente.nodes.supervisor import (
    INTENCIONES,
    _contexto_supervisor,
    _heuristica,
    _validar,
    supervisor,
)


def _state(text, tarea=None):
    return {
        "messages": [{"role": "user", "content": text}],
        "tarea": tarea or {},
        "meta": {},
    }


def test_v8_validar_coerce_invalida():
    assert _validar("cualquier_cosa") == "conversacion"
    for i in INTENCIONES:
        assert _validar(i) == i


def test_v8_supervisor_intencion_siempre_valida(monkeypatch):
    # Fuerza el fallback (sin red): la intención siempre cae en el set permitido.
    monkeypatch.setattr(
        "agente.nodes.supervisor.clasificar_intencion", lambda *a, **k: None
    )
    out = supervisor(_state("hola, buenas"))
    assert out["ruteo"]["intencion"] in INTENCIONES


def test_v11_sticky_cita_activa():
    tarea = {"tipo": "citas", "subestado": "RECOPILANDO"}
    intencion, _ = _heuristica("el martes estaría bien", _state("...", tarea))
    assert intencion == "agendar"


def test_pide_humano_sobreescribe_sticky():
    tarea = {"tipo": "citas", "subestado": "RECOPILANDO"}
    intencion, _ = _heuristica("mejor pásame con una persona", _state("...", tarea))
    assert intencion == "handoff"


def test_contexto_incluye_tarea_y_mensaje():
    ctx = _contexto_supervisor(
        _state("¿cuánto cuesta?", {"tipo": "citas", "subestado": "RECOPILANDO"})
    )
    assert "TAREA ACTIVA: citas/RECOPILANDO" in ctx
    assert "MENSAJE ACTUAL: ¿cuánto cuesta?" in ctx
