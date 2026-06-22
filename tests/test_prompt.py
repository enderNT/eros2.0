"""Tests del ensamblado de prompt (T8)."""

from agente.prompt import NUCLEO, construir_prompt


def _state(text="hola", perfil=None, tarea=None):
    return {
        "messages": [{"role": "user", "content": text}],
        "perfil": perfil or {},
        "tarea": tarea or {},
        "meta": {},
    }


def test_dos_breakpoints_y_perfil():
    p = construir_prompt(_state(perfil={"identidad": {"nombre": "Ana"}}), "BLOQUE FAQ")
    assert len(p["system"]) == 2
    assert all(b["cache_control"]["type"] == "ephemeral" for b in p["system"])
    assert NUCLEO[:25] in p["system"][0]["text"]
    assert "BLOQUE FAQ" in p["system"][0]["text"]
    assert "Ana" in p["system"][1]["text"]


def test_recordatorio_en_turno_usuario():
    # El recordatorio va como <system-reminder> en el turno del usuario, NO como role:system
    # (evita el 400 "role 'system' is not supported on this model").
    p = construir_prompt(_state(tarea={"tipo": "citas", "subestado": "RECOPILANDO"}), "X")
    ultimo = p["messages"][-1]
    assert ultimo["role"] == "user"
    assert "<system-reminder>" in ultimo["content"]
    assert "cita en curso" in ultimo["content"]
    assert all(m["role"] != "system" for m in p["messages"])


def test_sin_tarea_recordatorio_neutro():
    p = construir_prompt(_state(), "X")
    assert "ninguna en curso" in p["messages"][-1]["content"]


def test_sin_perfil_un_solo_bloque():
    p = construir_prompt(_state(), "X", incluir_perfil=False)
    assert len(p["system"]) == 1
