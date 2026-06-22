"""Tests del pre-chequeo de crisis (ADR 0003)."""

import agente.llm as L


def test_fallback_keywords_detecta(monkeypatch):
    # Sin API key → red de seguridad por palabras clave.
    monkeypatch.setattr(L, "get_client", lambda: None)
    assert L.detectar_crisis("estoy pensando en suicidarme") is True
    assert L.detectar_crisis("quiero quitarme la vida") is True


def test_fallback_keywords_no_falso_positivo(monkeypatch):
    monkeypatch.setattr(L, "get_client", lambda: None)
    assert L.detectar_crisis("¿cuánto cuesta la valoración?") is False
    assert L.detectar_crisis("hola, buenas tardes") is False


def test_usa_clasificador_cuando_hay_cliente(monkeypatch):
    class FakeOut:
        crisis = True

    class FakeResp:
        parsed_output = FakeOut()

    class FakeClient:
        class messages:
            @staticmethod
            def parse(**kwargs):
                return FakeResp()

    monkeypatch.setattr(L, "get_client", lambda: FakeClient())
    assert L.detectar_crisis("mensaje ambiguo") is True


def test_cae_a_fallback_si_clasificador_explota(monkeypatch):
    class FakeClient:
        class messages:
            @staticmethod
            def parse(**kwargs):
                raise RuntimeError("boom")

    monkeypatch.setattr(L, "get_client", lambda: FakeClient())
    # El texto trae señal → el fallback la atrapa pese al fallo del clasificador.
    assert L.detectar_crisis("quiero matarme") is True
    assert L.detectar_crisis("¿tienen estacionamiento?") is False
