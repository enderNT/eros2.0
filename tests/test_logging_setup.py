import json
import logging
from io import StringIO

from agente.logging_setup import JsonFormatter, RedactionFilter, mask_phone, setup_logging


def _record(**extra) -> logging.LogRecord:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "turn handled", (), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_mask_phone_is_stable_and_keeps_only_last_two():
    masked_a = mask_phone("+1 205-294-3796")
    masked_b = mask_phone("+12052943796")
    assert masked_a == masked_b
    assert masked_a.endswith(":96")
    assert "2052943796" not in masked_a


def test_filter_drops_denied_keys():
    record = _record(text="patient words", body="x", password="p", turn_id="t-1")
    RedactionFilter().filter(record)
    assert not hasattr(record, "text")
    assert not hasattr(record, "body")
    assert not hasattr(record, "password")
    assert record.turn_id == "t-1"
    assert record.getMessage() == "turn handled"


def test_filter_masks_phone_keys():
    record = _record(contact_phone="+525512345678")
    RedactionFilter().filter(record)
    assert record.contact_phone.endswith(":78")
    assert "55123456" not in record.contact_phone


def test_formatter_emits_json_with_extras():
    record = _record(turn_id="t-1", muted=True)
    RedactionFilter().filter(record)
    payload = json.loads(JsonFormatter().format(record))
    assert payload["event"] == "turn handled"
    assert payload["level"] == "INFO"
    assert payload["turn_id"] == "t-1"
    assert payload["muted"] is True
    assert payload["ts"]


def test_message_body_never_reaches_the_log_line():
    logger = logging.getLogger("test.redaction")
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info(
            "inbound stored",
            extra={"text": "very private patient words", "message_id": "m-1"},
        )
    finally:
        logger.removeHandler(handler)
    output = stream.getvalue()
    assert "very private patient words" not in output
    payload = json.loads(output.strip())
    assert payload["message_id"] == "m-1"


def test_setup_logging_configures_root_logger():
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        setup_logging("WARNING")
        assert root.level == logging.WARNING
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
    finally:
        root.handlers[:] = original_handlers
        root.setLevel(original_level)
