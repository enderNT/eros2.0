"""Configuración leída del entorno (.env / variables de Coolify)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""

    # Modelos: Haiku para clasificación/crisis (rápido y barato), Opus para los agentes.
    model_supervisor: str = "claude-haiku-4-5"
    model_crisis: str = "claude-haiku-4-5"
    model_agente: str = "claude-opus-4-8"

    # Memoria corta (checkpointer SQLite)
    checkpoint_db_path: str = "data/checkpoints.sqlite"
    history_window: int = 10

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

    # Memoria larga (store propio), Wiki factual y Playbook de directrices
    store_db_path: str = "data/store.sqlite"
    wiki_path: str = "wiki.md"
    playbook_path: str = "playbook.md"

    # Observabilidad LLM (Postgres). Si está vacío, el logger queda inactivo.
    database_url: str = ""

    # Loop del agente
    max_iteraciones: int = 6  # tope de vueltas tool-use → respuesta

    log_level: str = "INFO"


settings = Settings()
