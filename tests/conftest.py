import pytest

from agente.adapters.store import db as store_db
from agente.adapters.store.contacts import SqliteContactsRepository
from agente.adapters.store.messages import SqliteMessagesRepository
from agente.adapters.store.mutes import SqliteMutesRepository
from agente.config import Settings

REQUIRED_OVERRIDES = {
    "anthropic_api_key": "sk-ant-test",
    "kapso_api_key": "kapso-test",
    "kapso_phone_number_id": "1087343774471931",
    "kapso_webhook_secret": "whsec-test",
    "calendly_token": "calendly-test",
    "calendly_event_type_uri": "https://api.calendly.com/event_types/test",
    "panel_password": "panel-password-test",
    "panel_session_secret": "panel-session-test",
    "crisis_message": "Si estás en riesgo inmediato llama al 911 o acude a urgencias.",
}


@pytest.fixture()
def make_settings(tmp_path):
    def _make(**overrides) -> Settings:
        kwargs = REQUIRED_OVERRIDES | {"db_path": tmp_path / "agente.db"} | overrides
        return Settings(_env_file=None, **kwargs)

    return _make


@pytest.fixture()
def settings(make_settings) -> Settings:
    return make_settings()


@pytest.fixture()
def db_conn(tmp_path):
    conn = store_db.connect(tmp_path / "store.db")
    store_db.migrate(conn)
    yield conn
    conn.close()


@pytest.fixture()
def contacts(db_conn):
    return SqliteContactsRepository(db_conn)


@pytest.fixture()
def messages(db_conn):
    return SqliteMessagesRepository(db_conn)


@pytest.fixture()
def mutes(db_conn):
    return SqliteMutesRepository(db_conn)
