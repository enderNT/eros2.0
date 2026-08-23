"""Application settings.

Loaded once at startup (see `agente.app`) and injected everywhere; no module
constructs a `Settings` object at import time. Every field maps 1:1 to an
environment variable (the field name in uppercase) and is mirrored in
`.env.example`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Clinic-facing placeholders carry this marker until the clinic writes the real
# text. Boot must fail loudly while it is present, not serve a placeholder to a
# patient.
PLACEHOLDER_MARKER = "<<pendiente"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Anthropic
    anthropic_api_key: str
    anthropic_model_conversation: str = "claude-sonnet-5"
    anthropic_model_crisis: str = "claude-haiku-4-5-20251001"
    anthropic_model_summarization: str = "claude-haiku-4-5-20251001"
    anthropic_max_tokens: int = 4096
    anthropic_thinking_type: Literal["adaptive", "disabled"] = "adaptive"
    anthropic_thinking_display: Literal["omitted", "summarized"] = "omitted"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    anthropic_max_iterations: int = 6

    # Kapso (WhatsApp channel)
    kapso_api_key: str
    kapso_phone_number_id: str
    kapso_webhook_secret: str
    kapso_base_url: str = "https://api.kapso.ai/meta/whatsapp/v24.0"

    # Calendly
    calendly_token: str
    calendly_event_type_uri: str
    calendly_timezone: str = "America/Mexico_City"
    calendly_location_kind: str = "physical"
    calendly_location_value: str = ""
    calendly_scheduling_link: str = ""
    calendly_signing_key: str = ""
    # Calendly requires an invitee email on every booking. Reserving on the
    # patient's behalf means we supply it, and asking the patient for theirs adds
    # a turn of friction to collect an address nobody reads: the confirmation
    # goes out over WhatsApp. One clinic address for every booking is the whole
    # answer — and it also means the patient never receives Calendly's own mail,
    # so nobody reschedules from a link behind our back (see C05).
    calendly_invitee_email: str = ""

    # Storage
    db_path: Path
    content_dir: Path = Path("content")

    # Control panel
    panel_password: str
    panel_session_secret: str

    # Behaviour
    debounce_seconds: float = 4.0
    window_token_budget: int = 2000
    overlap_turns: int = 1
    reply_max_chunks: int = 3
    reply_chunk_chars: int = 600
    reply_chunk_delay_seconds: float = 1.0
    # Cada cuánto despierta el bucle que vacía el outbox. Un solo intervalo para
    # los dos avisos: lo que cambia entre ellos es cuándo vencen, no cada cuánto
    # se mira si algo venció.
    outbox_poll_seconds: float = 15.0
    # Minutos de silencio antes de retomar a quien preguntó y no llegó a agendar.
    interest_followup_minutes: int = 60
    appointment_reminder_minutes: int = 1440
    # Los dos avisos automáticos se pueden apagar desde el panel. Estos son sólo
    # el valor de arranque: lo que mande es lo que haya guardado en `app_setting`.
    interest_followup_enabled: bool = True
    appointment_reminder_enabled: bool = True
    crisis_message: str

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @field_validator("crisis_message")
    @classmethod
    def crisis_message_is_real(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("crisis message is empty")
        if PLACEHOLDER_MARKER in value.lower():
            raise ValueError("crisis message is still the <<pendiente>> placeholder")
        return value


def load_settings() -> Settings:
    """Validate the environment once. Fails loudly, naming every bad field."""
    try:
        return Settings()
    except ValidationError as exc:
        lines = [f"  {str(err['loc'][-1]).upper()}: {err['msg']}" for err in exc.errors()]
        detail = "\n".join(lines)
        raise RuntimeError(
            f"configuration error — set these in the environment (.env) and restart:\n{detail}"
        ) from exc
