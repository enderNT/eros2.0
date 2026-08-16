"""Structured JSON logging with redaction enforced in the logger.

Message bodies and secrets never reach a log line: `RedactionFilter` drops
every extra field whose key is in `DENY_KEYS`, so a careless
`log.info(..., text=body)` cannot leak. Phone numbers are kept only as a
stable hash plus the last two digits (`mask_phone`).
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Field keys that are dropped from every log record, whatever the value.
DENY_KEYS = frozenset(
    {
        "text",
        "body",
        "content",
        "message_body",
        "transcript",
        "prompt",
        "password",
        "secret",
        "api_key",
        "token",
        "authorization",
        "cookie",
    }
)

# Field keys whose values are phone numbers: logged masked, never raw.
PHONE_KEYS = frozenset({"phone", "phone_number", "contact_phone"})

_RESERVED = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


def mask_phone(raw: Any) -> str:
    """Stable hash of the number plus its last two digits, and nothing else."""
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    digest = hashlib.sha256(digits.encode("utf-8")).hexdigest()[:8]
    return f"{digest}:{digits[-2:]}"


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        extras = set(vars(record)) - _RESERVED
        for key in extras:
            if key in DENY_KEYS:
                delattr(record, key)
            elif key in PHONE_KEYS:
                setattr(record, key, mask_phone(record.__dict__[key]))
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _RESERVED and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger: one JSON handler on stdout, redacted."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
