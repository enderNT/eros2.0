"""Tests de las herramientas: buscar_wiki, ver_horarios, agendar_cita (V3), escalar."""

import json

import agente.tools as T


# --- buscar_wiki: búsqueda por secciones -------------------------------------

_WIKI = """# Eros Neuronal

## Precios
La valoración inicial cuesta $1000. Las sesiones van de $1500 a $3500.

## Horarios
Atendemos de lunes a viernes, de 8am a 5pm.

## Ubicación
Sócrates 128, Polanco, CDMX.
"""


def _wiki(tmp_path, monkeypatch, contenido=_WIKI):
    p = tmp_path / "wiki.md"
    p.write_text(contenido, encoding="utf-8")
    monkeypatch.setattr(T.settings, "wiki_path", str(p))


def test_buscar_wiki_encuentra_seccion(tmp_path, monkeypatch):
    _wiki(tmp_path, monkeypatch)
    out = json.loads(T.ejecutar_tool("buscar_wiki", {"consulta": "precio valoración"}, {}))
    titulos = [r["seccion"] for r in out["resultados"]]
    assert "Precios" in titulos
    assert "$1000" in out["resultados"][0]["contenido"]


def test_buscar_wiki_acentos_indiferente(tmp_path, monkeypatch):
    _wiki(tmp_path, monkeypatch)
    # "ubicacion" sin tilde debe encontrar la sección "Ubicación".
    out = json.loads(T.ejecutar_tool("buscar_wiki", {"consulta": "ubicacion"}, {}))
    assert any(r["seccion"] == "Ubicación" for r in out["resultados"])


def test_buscar_wiki_sin_coincidencia_devuelve_indice(tmp_path, monkeypatch):
    _wiki(tmp_path, monkeypatch)
    out = json.loads(T.ejecutar_tool("buscar_wiki", {"consulta": "estacionamiento valet"}, {}))
    assert out["resultados"] == []
    assert "Precios" in out["indice"] and "Horarios" in out["indice"]


def test_buscar_wiki_sin_archivo(tmp_path, monkeypatch):
    monkeypatch.setattr(T.settings, "wiki_path", str(tmp_path / "noexiste.md"))
    out = json.loads(T.ejecutar_tool("buscar_wiki", {"consulta": "precio"}, {}))
    assert out["resultados"] == [] and "error" in out


# --- agendar_cita: la garantía dura ------------------------------------------

class _CalOK:
    def crear_invitee(self, **kw):
        from agente.calendly import ResultadoReserva
        return ResultadoReserva("ok", cancel_url="http://c", reschedule_url="http://r")


class _CalTaken:
    def crear_invitee(self, **kw):
        from agente.calendly import ResultadoReserva
        return ResultadoReserva("slot_taken", detail="ocupado")


class _CalError:
    def crear_invitee(self, **kw):
        from agente.calendly import ResultadoReserva
        return ResultadoReserva("error", detail="500 boom")


def _args():
    return {"nombre": "Ana", "correo": "a@x.com", "slot": "2026-07-01T18:00:00Z"}


def test_agendar_ok_registra_cita(monkeypatch):
    registros = []
    monkeypatch.setattr(T, "get_calendly", lambda: _CalOK())
    monkeypatch.setattr(T.settings, "calendly_event_type", "ev")
    monkeypatch.setattr(
        T, "get_store", lambda: type("S", (), {"registrar_cita": lambda self, u, f: registros.append((u, f))})()
    )
    out = json.loads(T.ejecutar_tool("agendar_cita", _args(), {"user_id": "u1"}))
    assert out["status"] == "ok"
    assert registros == [("u1", "2026-07-01T18:00:00Z")]


def test_agendar_slot_taken_no_registra(monkeypatch):
    monkeypatch.setattr(T, "get_calendly", lambda: _CalTaken())
    monkeypatch.setattr(T.settings, "calendly_event_type", "ev")
    out = json.loads(T.ejecutar_tool("agendar_cita", _args(), {"user_id": "u1"}))
    assert out["status"] == "slot_taken"


def test_agendar_error_no_confirma(monkeypatch):
    monkeypatch.setattr(T, "get_calendly", lambda: _CalError())
    monkeypatch.setattr(T.settings, "calendly_event_type", "ev")
    out = json.loads(T.ejecutar_tool("agendar_cita", _args(), {"user_id": "u1"}))
    assert out["status"] == "error"


def test_agendar_sin_calendly(monkeypatch):
    monkeypatch.setattr(T, "get_calendly", lambda: None)
    out = json.loads(T.ejecutar_tool("agendar_cita", _args(), {}))
    assert out["status"] == "error"


# --- ver_horarios ------------------------------------------------------------

def test_ver_horarios_lista(monkeypatch):
    class Cal:
        def available_times(self, ev, start, end):
            return [{"start_time": "2026-07-01T18:00:00Z"}, {"start_time": "2026-07-02T19:00:00Z"}]

    monkeypatch.setattr(T, "get_calendly", lambda: Cal())
    monkeypatch.setattr(T.settings, "calendly_event_type", "ev")
    out = json.loads(T.ejecutar_tool("ver_horarios", {}, {}))
    assert out["horarios"] == ["2026-07-01T18:00:00Z", "2026-07-02T19:00:00Z"]


def test_ver_horarios_sin_calendly(monkeypatch):
    monkeypatch.setattr(T, "get_calendly", lambda: None)
    out = json.loads(T.ejecutar_tool("ver_horarios", {}, {}))
    assert out["horarios"] == []


# --- escalar_a_humano --------------------------------------------------------

def test_escalar_apaga_bot_y_marca_ctx(monkeypatch):
    acciones = []

    class CW:
        def set_atributo(self, c, k, v):
            acciones.append((c, k, v))

    monkeypatch.setattr(T, "get_chatwoot", lambda: CW())
    ctx = {"conversation_id": 7}
    out = json.loads(T.ejecutar_tool("escalar_a_humano", {"motivo": "lo pidió"}, ctx))
    assert out["status"] == "escalado"
    assert ctx["escalado"] is True
    assert (7, "bot_activo", False) in acciones


def test_tool_desconocida():
    out = json.loads(T.ejecutar_tool("inexistente", {}, {}))
    assert "error" in out
