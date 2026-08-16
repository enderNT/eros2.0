from fastapi.testclient import TestClient

from agente.app import create_app


def test_health_reports_version_and_database(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "ok"
    assert payload["version"]


def test_health_reports_an_unreachable_database(settings, tmp_path):
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    settings.db_path = blocked  # a directory cannot be a SQLite file
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "degraded"
    assert "unreachable" in payload["database"]
