from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agente.adapters.store.contacts import SqliteContactsRepository
from agente.adapters.store.messages import SqliteMessagesRepository
from agente.adapters.store.mutes import SqliteMutesRepository
from agente.adapters.store.outbox import SqliteOutboxRepository
from agente.adapters.store.settings import SqliteRuntimeSettingsRepository
from agente.app import create_app
from agente.domain.contacts import ContactKey, mask_phone
from agente.ports.channel import ConversationList, ConversationRow

CONTACT = "+12052943796"

# The shell is a build artifact: skip rather than fail when the panel has not
# been compiled, so `pytest` on a fresh clone reports the reason instead of a
# missing file.
_SHELL = Path(__file__).resolve().parents[1] / "src/agente/web/static/panel/index.html"


class FakeChannel:
    async def aclose(self) -> None:
        pass

    async def list_conversations(self, *_args, **_kwargs) -> ConversationList:
        return ConversationList(
            [
                ConversationRow(
                    "conversation-1",
                    "Paciente",
                    CONTACT,
                    "Hola",
                    datetime(2026, 8, 16, tzinfo=UTC),
                    "active",
                )
            ],
            None,
        )


def _login(client: TestClient) -> None:
    response = client.post("/admin/api/login", json={"password": "panel-password-test"})
    assert response.status_code == 200
    assert response.json() == {"authed": True}


def _key(settings) -> dict[str, str]:
    return {"phone_number_id": settings.kapso_phone_number_id, "contact_phone": CONTACT}


def test_api_requires_a_session(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/admin/api/state").status_code == 401
        assert client.get("/admin/api/traces").status_code == 401
        assert client.post("/admin/api/global", json={"muted": True}).status_code == 401
        # The session probe is the one anonymous route: the SPA asks it to
        # decide whether to draw the login form.
        assert client.get("/admin/api/session").json() == {"authed": False}


@pytest.mark.skipif(not _SHELL.is_file(), reason="run `npm --prefix panel-ui run build`")
def test_the_shell_is_served_without_a_session_and_carries_no_data(settings):
    """The SPA shell has no patient data in it, so it is not behind the cookie."""
    with TestClient(create_app(settings)) as client:
        response = client.get("/admin")
        traces = client.get("/admin/traces")
    assert response.status_code == 200
    assert traces.status_code == 200
    assert "/admin/static/panel/assets/" in response.text
    assert CONTACT not in response.text


def test_a_wrong_password_is_rejected(settings):
    with TestClient(create_app(settings)) as client:
        assert client.post("/admin/api/login", json={"password": "nope"}).status_code == 401
        assert client.get("/admin/api/state").status_code == 401


def test_state_lists_one_row_per_contact_with_a_masked_phone(settings):
    with TestClient(create_app(settings)) as client:
        client.app.state.channel = FakeChannel()
        _login(client)
        state = client.get("/admin/api/state").json()

    assert state["phone_number_id"] == settings.kapso_phone_number_id
    assert state["error"] is None
    assert state["global_muted"] is False
    assert state["number_muted"] is False
    assert state["appointment_reminder"] == {
        "minutes": 1440,
        "min": 1,
        "max": 10080,
        "enabled": True,
    }
    (contact,) = state["contacts"]
    assert contact["name"] == "Paciente"
    assert contact["masked_phone"] == mask_phone(CONTACT)
    # The raw phone still travels: the mute key is built from it.
    assert contact["phone"] == CONTACT
    assert contact["mute"] is None
    assert contact["appointment"] is None


def test_contact_mute_round_trip(settings):
    with TestClient(create_app(settings)) as client:
        client.app.state.channel = FakeChannel()
        _login(client)
        response = client.post(
            "/admin/api/mute", json={**_key(settings), "muted": True, "expires_in": 3600}
        )
        assert response.status_code == 200
        assert response.json()["mute"]["muted_until"] is not None

        mutes = SqliteMutesRepository(client.app.state.db)
        key = ContactKey(settings.kapso_phone_number_id, CONTACT)
        assert mutes.is_bot_muted(key, datetime.now(UTC))
        assert mutes.audit_trail()[0].action == "contact_muted"

        cleared = client.post("/admin/api/mute", json={**_key(settings), "muted": False})
        assert cleared.json() == {"mute": None}
        assert not mutes.is_bot_muted(key, datetime.now(UTC))


def test_number_and_global_mutes_round_trip(settings):
    with TestClient(create_app(settings)) as client:
        _login(client)
        number = client.post(
            "/admin/api/number-mute",
            json={"phone_number_id": settings.kapso_phone_number_id, "muted": True},
        )
        global_response = client.post("/admin/api/global", json={"muted": True})
        assert number.json() == {"number_muted": True}
        assert global_response.json() == {"global_muted": True}

        mutes = SqliteMutesRepository(client.app.state.db)
        assert mutes.global_mute() is not None
        assert mutes.number_mute(settings.kapso_phone_number_id) is not None


def test_interest_followup_setting_is_its_own_control(settings):
    """Su propio ajuste, no un alias del recordatorio: mover uno no mueve el otro."""
    with TestClient(create_app(settings)) as client:
        _login(client)
        assert client.post("/admin/api/interest-followup", json={"minutes": 5}).json() == {
            "minutes": 5
        }
        runtime = SqliteRuntimeSettingsRepository(client.app.state.db)
        assert runtime.interest_followup_minutes(default=60) == 5
        assert runtime.appointment_reminder_minutes(default=1440) == 1440

        # Cero no vale: escribir en el mismo instante en que acabas de contestar
        # no es un seguimiento.
        assert client.post("/admin/api/interest-followup", json={"minutes": 0}).status_code == 422
        assert client.post("/admin/api/interest-followup", json={"minutes": 91}).status_code == 422
        assert runtime.interest_followup_minutes(default=60) == 5


def test_panel_state_exposes_the_two_automatic_notices(settings):
    with TestClient(create_app(settings)) as client:
        _login(client)
        state = client.get("/admin/api/state").json()
        assert state["interest_followup"] == {
            "minutes": 60,
            "min": 1,
            "max": 90,
            "enabled": True,
        }
        assert state["appointment_reminder"]["max"] == 10080
        assert state["interest_followup"] is not state["appointment_reminder"]
        # Y no queda rastro del tercero, el que colgaba de un enlace de reserva.
        assert "booking_followup" not in state


def test_interest_followup_send_reports_when_there_is_nothing_pending(settings):
    with TestClient(create_app(settings)) as client:
        _login(client)
        response = client.post(
            "/admin/api/interest-followup-send",
            json={
                "phone_number_id": settings.kapso_phone_number_id,
                "contact_phone": "+525512345678",
            },
        )
        assert response.json() == {"result": "missing"}


def test_appointment_reminder_setting_saves_and_refuses_out_of_range(settings):
    with TestClient(create_app(settings)) as client:
        _login(client)
        assert client.post(
            "/admin/api/appointment-reminder-settings", json={"minutes": 2}
        ).json() == {"minutes": 2}
        runtime = SqliteRuntimeSettingsRepository(client.app.state.db)
        assert runtime.appointment_reminder_minutes(default=1440) == 2

        too_long = client.post("/admin/api/appointment-reminder-settings", json={"minutes": 10081})
        assert too_long.status_code == 422
        assert runtime.appointment_reminder_minutes(default=1440) == 2


def test_one_row_per_contact_keeps_the_most_recent_conversation():
    from agente.web.panel import one_row_per_contact

    def row(conv_id, phone, day, status="ended"):
        return ConversationRow(
            conversation_id=conv_id,
            contact_name="Gabo",
            contact_phone=phone,
            last_message_text=f"m{day}",
            last_activity_at=datetime(2026, 8, day, 12, tzinfo=UTC),
            status=status,
        )

    rows, counts = one_row_per_contact(
        [
            row("c1", "+525619878083", 10),
            row("c3", "+525512345678", 12),
            row("c2", "+525619878083", 17, status="active"),
        ]
    )
    assert [r.conversation_id for r in rows] == ["c2", "c3"]  # newest contact first
    assert counts["+525619878083"] == 2
    assert counts["+525512345678"] == 1


def test_conversations_without_a_phone_are_not_merged_together():
    from agente.web.panel import one_row_per_contact

    anonymous = [
        ConversationRow("c1", None, None, None, None, "ended"),
        ConversationRow("c2", None, None, None, None, "ended"),
    ]
    rows, counts = one_row_per_contact(anonymous)
    assert len(rows) == 2
    assert counts == {"c1": 1, "c2": 1}


def test_a_contact_without_a_phone_gets_no_switches(settings):
    """No phone means no mute key, so the row carries no contact state."""

    class AnonymousChannel(FakeChannel):
        async def list_conversations(self, *_args, **_kwargs) -> ConversationList:
            return ConversationList([ConversationRow("c1", None, None, None, None, "ended")], None)

    with TestClient(create_app(settings)) as client:
        client.app.state.channel = AnonymousChannel()
        _login(client)
        (contact,) = client.get("/admin/api/state").json()["contacts"]
    assert contact["phone"] is None
    assert contact["masked_phone"] is None
    assert contact["mute"] is None


def test_reset_requires_a_session(settings):
    with TestClient(create_app(settings)) as client:
        response = client.post("/admin/api/reset", json=_key(settings))
    assert response.status_code == 401


def test_reset_erases_the_contact_and_audits_it(settings):
    """Everything about the contact goes, in one transaction, with a trail."""
    key = ContactKey(settings.kapso_phone_number_id, CONTACT)
    now = datetime(2026, 8, 16, 12, tzinfo=UTC)
    app = create_app(settings)
    with TestClient(app) as client:
        messages = SqliteMessagesRepository(app.state.db)
        messages.add_inbound(key, "in-1", "hola", now)
        messages.add_outbound(key, "out-1", "buenas", now)
        SqliteMutesRepository(app.state.db).set_mute(key, now, actor="test", reason="test")
        app.state.channel = FakeChannel()
        _login(client)

        response = client.post("/admin/api/reset", json=_key(settings))
        assert response.status_code == 200
        assert response.json()["purged"] > 0
        assert response.json()["mute"] is None
        assert messages.window(key, 10) == []
        mutes = SqliteMutesRepository(app.state.db)
        assert mutes.contact_mute(key) is None
        assert any(entry.action == "contact_purged" for entry in mutes.audit_trail())


def test_reset_on_a_contact_with_nothing_stored_is_harmless(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.channel = FakeChannel()
        _login(client)
        response = client.post("/admin/api/reset", json=_key(settings))
    assert response.status_code == 200
    assert response.json()["purged"] == 0


def test_traces_are_listed_for_a_session(settings):
    with TestClient(create_app(settings)) as client:
        _login(client)
        response = client.get("/admin/api/traces")
    assert response.status_code == 200
    assert response.json() == {"traces": []}


def test_logout_drops_the_session(settings):
    with TestClient(create_app(settings)) as client:
        _login(client)
        assert client.get("/admin/api/session").json() == {"authed": True}
        client.post("/admin/api/logout")
        assert client.get("/admin/api/session").json() == {"authed": False}
        assert client.get("/admin/api/state").status_code == 401


def test_the_two_switches_are_independent_routes(settings):
    """Cada aviso tiene su interruptor: apagar uno deja el otro encendido."""
    with TestClient(create_app(settings)) as client:
        _login(client)
        assert client.post(
            "/admin/api/interest-followup-enabled", json={"enabled": False}
        ).json() == {"enabled": False}

        state = client.get("/admin/api/state").json()
        assert state["interest_followup"]["enabled"] is False
        assert state["appointment_reminder"]["enabled"] is True

        assert client.post(
            "/admin/api/appointment-reminder-enabled", json={"enabled": False}
        ).json() == {"enabled": False}
        assert client.post(
            "/admin/api/interest-followup-enabled", json={"enabled": True}
        ).json() == {"enabled": True}

        state = client.get("/admin/api/state").json()
        assert state["interest_followup"]["enabled"] is True
        assert state["appointment_reminder"]["enabled"] is False


def test_turning_a_follow_up_off_empties_what_was_already_queued(settings):
    """Apagar borra la cola, no sólo deja de encolar.

    Si la fila sobreviviera, volver a encender el interruptor un mes después
    soltaría de golpe un "¿sigues por ahí?" a quien se calló en marzo.
    """
    key = ContactKey(settings.kapso_phone_number_id, "+525512345678")
    with TestClient(create_app(settings)) as client:
        _login(client)
        db = client.app.state.db
        SqliteContactsRepository(db).ensure_contact(key, datetime.now(UTC))
        client.app.state.interest_followups.schedule_from_outbound(
            key, "lo que dijo el bot", datetime.now(UTC)
        )
        outbox = SqliteOutboxRepository(db)
        assert outbox.pending_interest_followup(key) is not None

        client.post("/admin/api/interest-followup-enabled", json={"enabled": False})
        assert outbox.pending_interest_followup(key) is None

        # Y apagado tampoco vuelve a armarse por mucho que el bot siga hablando.
        client.app.state.interest_followups.schedule_from_outbound(
            key, "otra respuesta", datetime.now(UTC)
        )
        assert outbox.pending_interest_followup(key) is None
