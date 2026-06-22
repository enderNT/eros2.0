"""Configuración leída del entorno (.env / variables de Coolify)."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""

    # Modelos: Haiku para clasificación/crisis (rápido y barato), Opus para los agentes.
    model_supervisor: str = "claude-haiku-4-5"
    model_crisis: str = "claude-haiku-4-5"
    model_agente: str = "claude-opus-4-8"

    # Memoria conversacional
    history_window: int = 10
    history_compact_limit: int = 16
    history_overlap: int = 1

    # Canal (Chatwoot)
    chatwoot_base_url: str = ""
    chatwoot_api_token: str = ""
    chatwoot_account_id: str = ""
    chatwoot_webhook_token: str = ""  # opcional: secreto compartido para el webhook

    # Agendamiento (Calendly)
    calendly_token: str = ""
    calendly_event_type: str = ""  # URI del tipo de evento (un solo tipo por ahora)
    calendly_timezone: str = "America/Mexico_City"
    calendly_location_kind: str = "physical"
    calendly_scheduling_link: str = ""  # link de autoservicio

    # Crisis: mensaje/recursos aprobados por la clínica (hueco — T17)
    crisis_message: str = "<<recursos de crisis — definir con la clínica>>"

    # Wiki factual y Playbook de directrices
    wiki_path: str = "wiki.md"
    playbook_path: str = "playbook.md"

    # Postgres para memoria + observabilidad. Si está vacío, el logger queda inactivo
    # y el store no puede operar.
    database_url: str = ""

    # Loop del agente
    max_iteraciones: int = 6  # tope de vueltas tool-use → respuesta
    agent_max_tokens: int = 4096
    agent_thinking_type: Literal["adaptive", "disabled"] = "adaptive"
    agent_thinking_display: Literal["omitted", "summarized"] = "omitted"
    agent_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"

    log_level: str = "INFO"


settings = Settings()
