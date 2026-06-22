"""Tests del cliente Calendly (T3 · V3 · V10). Sin red: httpx.MockTransport."""

import httpx

from agente.calendly import CalendlyClient


def _client(handler):
    transport = httpx.MockTransport(handler)
    http = httpx.Client(base_url="https://api.calendly.com", transport=transport)
    return CalendlyClient("tok", http=http)


_DATOS = dict(
    event_type="ev",
    start_time="2026-07-01T18:00:00Z",
    nombre="Ana",
    correo="ana@mail.com",
    timezone="America/Mexico_City",
    location_kind="physical",
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
