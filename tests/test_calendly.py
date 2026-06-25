"""Tests del cliente Calendly (T3 · V3 · V10). Sin red: httpx.MockTransport."""

import json

import httpx

import agente.calendly as C
from agente.calendly import CalendlyClient


def _client(handler):
    transport = httpx.MockTransport(handler)
    http = httpx.Client(base_url="https://api.calendly.com", transport=transport)
    return CalendlyClient("tok", http=http)


def _client_with_headers(handler):
    transport = httpx.MockTransport(handler)
    http = httpx.Client(
        base_url="https://api.calendly.com",
        headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
        transport=transport,
    )
    return CalendlyClient("tok", http=http)


_DATOS = dict(
    event_type="ev",
    start_time="2026-07-01T18:00:00Z",
    nombre="Ana",
    correo="ana@mail.com",
    timezone="America/Mexico_City",
    location_kind="physical",
    location_value="Av. Siempre Viva 123, Col. Centro, CDMX",
)


def test_crear_invitee_ok():
    def h(req):
        return httpx.Response(
            201, json={"resource": {"cancel_url": "c", "reschedule_url": "r"}}
        )

    res = _client(h).crear_invitee(**_DATOS)
    assert res.status == "ok"
    assert res.cancel_url == "c" and res.reschedule_url == "r"


def test_crear_invitee_slot_taken():
    def h(req):
        return httpx.Response(409, text="no longer available")

    assert _client(h).crear_invitee(**_DATOS).status == "slot_taken"


def test_crear_invitee_error():
    def h(req):
        return httpx.Response(500, text="boom")

    assert _client(h).crear_invitee(**_DATOS).status == "error"


def test_crear_invitee_400_es_peticion_no_utilizable():
    def h(req):
        return httpx.Response(400, json={"message": "The supplied parameters are invalid."})

    res = _client(h).crear_invitee(**_DATOS)
    assert res.status == "slot_taken"
    assert "invalid" in res.detail


def test_crear_invitee_fisico_envia_location_location():
    """kind physical → el payload debe incluir location.location con la dirección."""
    captura = {}

    def h(req):
        captura["body"] = json.loads(req.content)
        return httpx.Response(201, json={"resource": {}})

    res = _client(h).crear_invitee(**_DATOS)
    assert res.status == "ok"
    assert captura["body"]["location"] == {
        "kind": "physical",
        "location": "Av. Siempre Viva 123, Col. Centro, CDMX",
    }


def test_crear_invitee_conferencia_omite_location_location():
    """kind de conferencia → solo lleva kind; Calendly genera el enlace."""
    captura = {}

    def h(req):
        captura["body"] = json.loads(req.content)
        return httpx.Response(201, json={"resource": {}})

    datos = {**_DATOS, "location_kind": "zoom_conference", "location_value": None}
    res = _client(h).crear_invitee(**datos)
    assert res.status == "ok"
    assert captura["body"]["location"] == {"kind": "zoom_conference"}


def test_crear_invitee_fisico_sin_valor_falla_en_preflight():
    """kind que exige location pero sin valor → error sin tocar la red."""
    def h(req):
        raise AssertionError("no debe llamar Calendly sin location.location")

    datos = {**_DATOS, "location_value": None}
    res = _client(h).crear_invitee(**datos)
    assert res.status == "error"
    assert "location.location" in res.detail


def test_available_times_envia_params():
    captura = {}

    def h(req):
        captura["url"] = str(req.url)
        return httpx.Response(
            200,
            json={"collection": [{"start_time": "2026-07-01T18:00:00Z", "status": "available"}]},
        )

    out = _client(h).available_times("ev", "2026-07-01T00:00:00Z", "2026-07-07T00:00:00Z")
    assert "event_type=ev" in captura["url"]
    assert len(out) == 1


def test_crear_invitee_registra_http_semantico(monkeypatch):
    registros = []

    class Logger:
        def record(self, **kwargs):
            registros.append(kwargs)

    monkeypatch.setattr(C, "get_llm_logger", lambda: Logger())

    def h(req):
        return httpx.Response(201, json={"resource": {"uri": "invitee", "event": "event"}})

    ctx = {"conversation_id": "c1", "flow_id": "f1", "message_id": "m1"}
    res = _client_with_headers(h).crear_invitee(**_DATOS, ctx=ctx)

    assert res.status == "ok"
    assert len(registros) == 1
    registro = registros[0]
    assert registro["provider"] == "calendly"
    assert registro["operation"] == "calendly.create_invitee"
    assert registro["status"] == "ok"
    assert registro["flow_id"] == "f1"
    assert registro["metadata"]["calendly_http"] is True

    traza = registro["request_text"]
    assert "Calendly POST https://api.calendly.com/invitees" in traza
    assert '"authorization": "***"' in traza
    assert _DATOS["start_time"] in traza

    body = json.loads(registro["metadata"]["request_body_text"])
    assert body["invitee"]["email"] == _DATOS["correo"]

    output = json.loads(registro["response_text"])
    assert output["status_code"] == 201
    assert output["body"]["resource"]["uri"] == "invitee"


def test_crear_invitee_http_error_se_marca_error(monkeypatch):
    registros = []

    class Logger:
        def record(self, **kwargs):
            registros.append(kwargs)

    monkeypatch.setattr(C, "get_llm_logger", lambda: Logger())

    def h(req):
        return httpx.Response(422, json={"message": "slot unavailable"})

    res = _client(h).crear_invitee(**_DATOS, ctx={"flow_id": "f1"})

    assert res.status == "slot_taken"
    assert registros[0]["status"] == "error"
    output = json.loads(registros[0]["response_text"])
    assert output["status_code"] == 422
    assert output["body"]["message"] == "slot unavailable"


def test_crear_invitee_start_time_pasado_no_llama_calendly(monkeypatch):
    registros = []

    class Logger:
        def record(self, **kwargs):
            registros.append(kwargs)

    monkeypatch.setattr(C, "get_llm_logger", lambda: Logger())

    def h(req):
        raise AssertionError("no debe llamar Calendly con start_time pasado")

    datos = {**_DATOS, "start_time": "2000-01-01T18:00:00Z"}
    res = _client(h).crear_invitee(**datos, ctx={"flow_id": "f1"})

    assert res.status == "slot_taken"
    assert "futuro" in res.detail
    assert registros[0]["operation"] == "calendly.create_invitee.preflight"
    assert registros[0]["status"] == "error"
    assert registros[0]["metadata"]["calendly_trace"] is True
    body = json.loads(registros[0]["metadata"]["request_body_text"])
    assert body["start_time"] == "2000-01-01T18:00:00Z"
