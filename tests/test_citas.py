"""Tests de la máquina de Citas (T4) y extraer_slot (T5). V3 · V10 · V11."""

import agente.nodes.citas as C
from agente.calendly import ResultadoReserva
from agente.llm import SlotExtraido


def _state(text, tarea=None):
    return {
        "messages": [{"role": "user", "content": text}],
        "tarea": tarea or {},
        "meta": {},
    }


# --- T5: extraer_slot --------------------------------------------------------

def test_extraer_slot_encontrado(monkeypatch):
    monkeypatch.setattr(
        C, "extraer_slot_llm",
        lambda s, c: SlotExtraido(encontrado=True, start_time="2026-07-01T18:00:00Z"),
    )
    assert C._extraer_slot(_state("el martes a las 12")) == "2026-07-01T18:00:00Z"


def test_extraer_slot_no_encontrado(monkeypatch):
    monkeypatch.setattr(
        C, "extraer_slot_llm", lambda s, c: SlotExtraido(encontrado=False)
    )
    assert C._extraer_slot(_state("hola")) is None


# --- T4: entrada -------------------------------------------------------------

def test_entrada_sin_slot_ofrece_autoservicio(monkeypatch):
    monkeypatch.setattr(C, "_extraer_slot", lambda s: None)
    out = C.agente_citas(_state("quiero una cita"))
    assert out["tarea"]["subestado"] == "OFRECER_AUTOSERVICIO"
    assert out["tarea"]["link_enviado"] is True


def test_entrada_con_slot_va_a_recopilando(monkeypatch):
    monkeypatch.setattr(C, "_extraer_slot", lambda s: "2026-07-01T18:00:00Z")
    out = C.agente_citas(_state("agéndame el martes 12pm"))
    assert out["tarea"]["subestado"] == "RECOPILANDO"
    assert out["tarea"]["slot_elegido"] == "2026-07-01T18:00:00Z"
    assert out["tarea"]["pidiendo"] == "nombre"  # slot ya listo → pide datos


# --- T4: recopilación → confirmando -----------------------------------------

def test_recopilando_completa_y_pasa_a_confirmando(monkeypatch):
    monkeypatch.setattr(C, "_extraer_slot", lambda s: None)
    tarea = {
        "tipo": "citas",
        "subestado": "RECOPILANDO",
        "slot_elegido": "2026-07-01T18:00:00Z",
        "datos": {},
        "pidiendo": "nombre",
    }
    out = C.agente_citas(_state("Ana Pérez", tarea))
    assert out["tarea"]["datos"]["nombre"] == "Ana Pérez"
    assert out["tarea"]["pidiendo"] == "correo"
    out = C.agente_citas(_state("ana@mail.com", out["tarea"]))
    assert out["tarea"]["pidiendo"] == "asunto"
    out = C.agente_citas(_state("primera consulta", out["tarea"]))
    assert out["tarea"]["subestado"] == "CONFIRMANDO"


# --- T4: confirmando (V3) ----------------------------------------------------

def _tarea_confirmando():
    return {
        "tipo": "citas",
        "subestado": "CONFIRMANDO",
        "slot_elegido": "2026-07-01T18:00:00Z",
        "datos": {"nombre": "Ana", "correo": "a@a.com", "asunto": "x"},
    }


def test_confirmando_ok_confirma(monkeypatch):
    class FakeCal:
        def crear_invitee(self, **k):
            return ResultadoReserva("ok", cancel_url="c")

    monkeypatch.setattr(C, "get_calendly", lambda: FakeCal())
    monkeypatch.setattr(C.settings, "calendly_event_type", "ev")
    out = C.agente_citas(_state("sí", _tarea_confirmando()))
    assert out["tarea"]["subestado"] == "CONFIRMADA"
    assert out["salida"]["resultado"] == "resuelto"


def test_v3_error_nunca_confirma_y_escala(monkeypatch):
    class FakeCal:
        def crear_invitee(self, **k):
            return ResultadoReserva("error", detail="boom")

    monkeypatch.setattr(C, "get_calendly", lambda: FakeCal())
    monkeypatch.setattr(C.settings, "calendly_event_type", "ev")
    out = C.agente_citas(_state("sí", _tarea_confirmando()))
    assert out["tarea"]["subestado"] != "CONFIRMADA"  # V3
    assert out["salida"]["resultado"] == "fuera_de_alcance"  # → handoff


def test_slot_taken_vuelve_a_recopilando(monkeypatch):
    class FakeCal:
        def crear_invitee(self, **k):
            return ResultadoReserva("slot_taken")

        def available_times(self, *a, **k):
            return []

    monkeypatch.setattr(C, "get_calendly", lambda: FakeCal())
    monkeypatch.setattr(C.settings, "calendly_event_type", "ev")
    out = C.agente_citas(_state("sí", _tarea_confirmando()))
    assert out["tarea"]["subestado"] == "RECOPILANDO"
    assert out["tarea"]["slot_elegido"] is None


# --- T4: descarte ------------------------------------------------------------

def test_descarte_explicito_abandona():
    tarea = {"tipo": "citas", "subestado": "RECOPILANDO", "datos": {}, "pidiendo": "nombre"}
    out = C.agente_citas(_state("ya no, olvídalo", tarea))
    assert out["tarea"]["subestado"] == "ABANDONADA"
