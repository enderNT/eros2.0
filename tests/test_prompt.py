"""Tests del ensamblado del system prompt (loop ReAct).

La wiki ya NO va en el system (se consulta con buscar_wiki); el system es
núcleo + playbook (+ perfil).
"""

import agente.prompt as P
from agente.prompt import NUCLEO, construir_system


def test_un_solo_bloque_sin_perfil():
    bloques = construir_system(None)
    assert len(bloques) == 1
    assert bloques[0]["cache_control"]["type"] == "ephemeral"


def test_dos_bloques_con_perfil(monkeypatch):
    monkeypatch.setattr(P, "cargar_playbook", lambda: "DIRECTRIZ Y")
    bloques = construir_system({"identidad": {"nombre": "Ana"}})
    assert len(bloques) == 2
    assert all(b["cache_control"]["type"] == "ephemeral" for b in bloques)
    base = bloques[0]["text"]
    assert NUCLEO[:25] in base
    assert "DIRECTRIZ Y" in base
    assert "Ana" in bloques[1]["text"]


def test_nucleo_menciona_buscar_wiki():
    # El núcleo debe instruir consultar la herramienta, no una wiki inline.
    assert "buscar_wiki" in NUCLEO


def test_perfil_render_campos():
    txt = P.render_perfil({"identidad": {"nombre": "Leo"}, "memoria_larga": {"citas_previas": 2}})
    assert "Leo" in txt and "2" in txt
