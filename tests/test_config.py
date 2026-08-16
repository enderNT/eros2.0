from pathlib import Path

import pytest

from agente.config import load_settings

ENV_REQUIRED = {
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "KAPSO_API_KEY": "kapso-test",
    "KAPSO_PHONE_NUMBER_ID": "1087343774471931",
    "KAPSO_WEBHOOK_SECRET": "whsec-test",
    "CALENDLY_TOKEN": "calendly-test",
    "CALENDLY_EVENT_TYPE_URI": "https://api.calendly.com/event_types/test",
    "DB_PATH": "/tmp/agente-config-test.db",
    "PANEL_PASSWORD": "panel-password-test",
    "PANEL_SESSION_SECRET": "panel-session-test",
    "CRISIS_MESSAGE": "Llama al 911 si estás en peligro inmediato.",
}


@pytest.fixture()
def clean_env(monkeypatch, tmp_path):
    # chdir away from the repo so a developer's .env cannot leak into the test
    monkeypatch.chdir(tmp_path)
    for name in ENV_REQUIRED:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_load_settings_reads_env_and_defaults(clean_env):
    for name, value in ENV_REQUIRED.items():
        clean_env.setenv(name, value)
    cfg = load_settings()
    assert cfg.anthropic_api_key == "sk-ant-test"
    assert cfg.kapso_phone_number_id == "1087343774471931"
    assert cfg.db_path == Path("/tmp/agente-config-test.db")
    # defaults fixed by SPEC §5 / §4 / §8
    assert cfg.anthropic_model_conversation == "claude-sonnet-5"
    assert cfg.anthropic_model_crisis == "claude-haiku-4-5-20251001"
    assert cfg.anthropic_model_summarization == "claude-haiku-4-5-20251001"
    assert cfg.anthropic_max_iterations == 6
    assert cfg.debounce_seconds == 4.0
    assert cfg.overlap_turns == 1
    assert cfg.reply_max_chunks == 3
    assert cfg.reply_chunk_chars == 600


def test_missing_required_setting_fails_loudly(clean_env):
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    with pytest.raises(RuntimeError, match="KAPSO_API_KEY"):
        load_settings()


def test_placeholder_crisis_message_fails_boot(clean_env):
    for name, value in ENV_REQUIRED.items():
        clean_env.setenv(name, value)
    clean_env.setenv("CRISIS_MESSAGE", "<<pendiente: definir con la clínica>>")
    with pytest.raises(RuntimeError, match="CRISIS_MESSAGE"):
        load_settings()


def test_blank_crisis_message_fails_boot(clean_env):
    for name, value in ENV_REQUIRED.items():
        clean_env.setenv(name, value)
    clean_env.setenv("CRISIS_MESSAGE", "   ")
    with pytest.raises(RuntimeError, match="CRISIS_MESSAGE"):
        load_settings()
