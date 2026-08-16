"""SQLite connection, schema migrations and the health probe.

One file, WAL mode, foreign keys on (SPEC §10). Migrations live in
`migrations/NNNN_name.sql`, are applied in version order, each inside a
single transaction that also records the version — so applying is
idempotent and a half-applied migration cannot exist. Migration files are
plain DDL and must not manage transactions themselves.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

from ...domain.errors import StoreError

_MIGRATION_NAME = re.compile(r"^(\d{4})_.+\.sql$")


def connect(path: Path) -> sqlite3.Connection:
    """Open the database with WAL and foreign keys enabled.

    `check_same_thread` is off because the connection is shared by design:
    the store layer is the single writer that serializes access (SPEC §4),
    and FastAPI may call it from more than one thread (test portal, thread
    pool). Per-call thread affinity would be false safety.
    """
    try:
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
    except sqlite3.Error as exc:
        raise StoreError(f"cannot open database {path}: {exc}") from exc
    conn.row_factory = sqlite3.Row
    return conn


def probe(path: Path) -> str | None:
    """None when the SQLite file is reachable and writable, else the reason."""
    try:
        conn = sqlite3.connect(path)
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return f"unreachable ({exc.__class__.__name__})"
    if not os.access(path, os.W_OK):
        return "not writable"
    return None


def migrate(
    conn: sqlite3.Connection, *, source: Path | None = None, now: datetime | None = None
) -> list[int]:
    """Apply every pending migration; return the versions applied this run."""
    moment = to_utc_iso(now if now is not None else datetime.now(UTC))
    try:
        with conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_version ("
                "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
        applied = {row["version"] for row in conn.execute("SELECT version FROM schema_version")}
        done: list[int] = []
        for version, script in _pending_migrations(source, applied):
            # executescript runs outside the implicit transaction handling, so the
            # migration DDL and its version record share one explicit transaction.
            conn.executescript(
                f"BEGIN;\n{script}\n"
                f"INSERT INTO schema_version (version, applied_at)"
                f" VALUES ({version}, '{moment}');\n"
                "COMMIT;"
            )
            done.append(version)
        return done
    except sqlite3.Error as exc:
        raise StoreError(f"migration failed: {exc}") from exc


def to_utc_iso(moment: datetime) -> str:
    """The storage form of every timestamp: UTC ISO-8601 (SPEC §10)."""
    if moment.tzinfo is None:
        raise StoreError(f"refusing to store a naive datetime: {moment!r}")
    return moment.astimezone(UTC).isoformat()


def optional_utc_iso(moment: datetime | None) -> str | None:
    return to_utc_iso(moment) if moment is not None else None


def parse_utc_iso(value: str) -> datetime:
    """Inverse of `to_utc_iso`; stored strings always carry the UTC offset."""
    return datetime.fromisoformat(value)


def _pending_migrations(source: Path | None, applied: set[int]) -> list[tuple[int, str]]:
    root = source if source is not None else resources.files("agente.adapters.store") / "migrations"
    pending: list[tuple[int, str]] = []
    for item in sorted(root.iterdir(), key=lambda entry: entry.name):
        match = _MIGRATION_NAME.match(item.name)
        if match is None:
            if item.name.endswith(".sql"):
                raise StoreError(f"badly named migration file: {item.name}")
            continue
        version = int(match.group(1))
        if version in applied:
            continue
        if any(seen == version for seen, _ in pending):
            raise StoreError(f"duplicate migration version {version:04d}")
        pending.append((version, item.read_text(encoding="utf-8")))
    return pending
