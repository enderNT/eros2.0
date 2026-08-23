"""Connection pragmas, migration machinery and the health probe (SPEC §10)."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from agente.adapters.store import db as store_db
from agente.adapters.store.settings import SqliteRuntimeSettingsRepository
from agente.app import create_app
from agente.domain.errors import StoreError

EXPECTED_TABLES = {
    "schema_version",
    "contact",
    "profile",
    "message",
    "summary",
    "mute",
    "number_mute",
    "global_state",
    "audit_log",
    "appointment",
    "llm_trace",
    "outbox",
    "app_setting",
}

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def _tables(conn) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row["name"] for row in rows if not row["name"].startswith("sqlite_")}


def test_connect_enables_wal_and_foreign_keys(tmp_path):
    conn = store_db.connect(tmp_path / "db.sqlite")
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_connect_raises_store_error_on_unusable_path(tmp_path):
    directory = tmp_path / "blocked"
    directory.mkdir()
    with pytest.raises(StoreError):
        store_db.connect(directory)


def test_migrate_creates_every_table(db_conn):
    assert _tables(db_conn) >= EXPECTED_TABLES


def test_migrate_records_the_applied_version(db_conn):
    rows = db_conn.execute("SELECT version FROM schema_version").fetchall()
    assert [row["version"] for row in rows] == [1, 2, 3, 4, 5, 6, 7, 8, 9]


def test_runtime_followup_setting_is_global_and_bounded(db_conn):
    settings = SqliteRuntimeSettingsRepository(db_conn)
    assert settings.interest_followup_minutes(default=60) == 60
    settings.set_interest_followup_minutes(1, NOW)
    assert settings.interest_followup_minutes(default=60) == 1
    assert settings.appointment_reminder_minutes(default=1440) == 1440
    settings.set_appointment_reminder_minutes(2, NOW)
    assert settings.appointment_reminder_minutes(default=1440) == 2
    with pytest.raises(ValueError, match="between 1 and 10080"):
        settings.set_appointment_reminder_minutes(10081, NOW)
    with pytest.raises(ValueError, match="between 1 and 90"):
        settings.set_interest_followup_minutes(91, NOW)
    with pytest.raises(ValueError, match="between 1 and 90"):
        settings.set_interest_followup_minutes(0, NOW)


def test_migrate_is_idempotent_and_preserves_data(db_conn):
    db_conn.execute(
        "INSERT INTO global_state (id, muted_at) VALUES (1, '2026-08-16T12:00:00+00:00')"
    )
    db_conn.commit()
    assert store_db.migrate(db_conn, now=NOW) == []
    assert db_conn.execute("SELECT COUNT(*) FROM global_state").fetchone()[0] == 1
    assert len(_tables(db_conn)) == len(EXPECTED_TABLES)


def test_migrate_applies_in_version_order(tmp_path):
    source = tmp_path / "migrations"
    source.mkdir()
    # Written out of order on purpose: naming, not filesystem order, rules.
    (source / "0002_second.sql").write_text("CREATE TABLE b (id INTEGER PRIMARY KEY);")
    (source / "0001_first.sql").write_text("CREATE TABLE a (id INTEGER PRIMARY KEY);")
    conn = store_db.connect(tmp_path / "db.sqlite")
    try:
        assert store_db.migrate(conn, source=source, now=NOW) == [1, 2]
        assert {"a", "b"} <= _tables(conn)
        rows = conn.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
        assert [row["version"] for row in rows] == [1, 2]
        assert store_db.migrate(conn, source=source, now=NOW) == []
    finally:
        conn.close()


def test_migrate_rejects_a_badly_named_sql_file(tmp_path):
    source = tmp_path / "migrations"
    source.mkdir()
    (source / "no_version.sql").write_text("CREATE TABLE a (id INTEGER PRIMARY KEY);")
    conn = store_db.connect(tmp_path / "db.sqlite")
    try:
        with pytest.raises(StoreError, match="badly named"):
            store_db.migrate(conn, source=source, now=NOW)
    finally:
        conn.close()


def test_to_utc_iso_converts_and_rejects_naive():
    assert store_db.to_utc_iso(NOW) == "2026-08-16T12:00:00+00:00"
    with pytest.raises(StoreError, match="naive"):
        store_db.to_utc_iso(datetime(2026, 8, 16, 12, 0))


def test_probe_reports_ok_and_unreachable(tmp_path):
    database = tmp_path / "db.sqlite"
    store_db.connect(database).close()
    assert store_db.probe(database) is None
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    assert "unreachable" in store_db.probe(blocked)


def test_boot_opens_and_migrates_the_database(settings):
    with TestClient(create_app(settings)) as client:
        assert client.app.state.db is not None
        assert _tables(client.app.state.db) >= EXPECTED_TABLES
        assert client.get("/health").json()["status"] == "ok"


def test_boot_survives_an_unopenable_database(settings, tmp_path):
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    settings.db_path = blocked
    with TestClient(create_app(settings)) as client:
        assert client.app.state.db is None
        response = client.get("/health")
    assert response.status_code == 503
    assert "unreachable" in response.json()["database"]
