from datetime import UTC, datetime

from fastapi.testclient import TestClient

from agente.adapters.store.messages import SqliteMessagesRepository
from agente.adapters.store.mutes import SqliteMutesRepository
from agente.adapters.store.settings import SqliteRuntimeSettingsRepository
from agente.app import create_app
from agente.domain.contacts import ContactKey, mask_phone
from agente.ports.channel import ConversationList, ConversationRow


class FakeChannel:
    async def aclose(self) -> None:
        pass

    async def list_conversations(self, *_args, **_kwargs) -> ConversationList:
        return ConversationList(
            [
                ConversationRow(
                    "conversation-1",
                    "Paciente",
                    "+12052943796",
                    "Hola",
                    datetime(2026, 8, 16, tzinfo=UTC),
                    "active",
                )
            ],
            None,
        )


def _login(client: TestClient) -> None:
    response = client.post(
        "/admin/login", data={"password": "panel-password-test"}, follow_redirects=False
    )
    assert response.status_code == 303


def test_admin_requires_session_and_serves_local_htmx(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/admin").status_code == 401
        assert client.get("/admin/traces").status_code == 401
        assert client.post("/admin/global", data={"muted": "true"}).status_code == 401
        response = client.get("/admin/static/htmx.min.js")
    assert response.status_code == 200
    assert len(response.text) > 1000


def test_panel_renders_live_fake_and_contact_mute_round_trip(settings):
    with TestClient(create_app(settings)) as client:
        client.app.state.channel = FakeChannel()
        _login(client)
        page = client.get("/admin")
        assert page.status_code == 200
        assert "Paciente" in page.text
        assert mask_phone("+12052943796") in page.text
        assert "Mutar número" in page.text

        response = client.post(
            "/admin/mute",
            data={
                "phone_number_id": settings.kapso_phone_number_id,
                "contact_phone": "+12052943796",
                "muted": "true",
                "expires_in": "3600",
            },
        )
        assert response.status_code == 200
        assert "Activar bot" in response.text
        assert "hasta" in response.text
        mutes = SqliteMutesRepository(client.app.state.db)
        key = ContactKey(settings.kapso_phone_number_id, "+12052943796")
        assert mutes.is_bot_muted(key, datetime.now(UTC))
        assert mutes.audit_trail()[0].action == "contact_muted"


def test_number_and_global_mutes_round_trip(settings):
    with TestClient(create_app(settings)) as client:
        _login(client)
        number = client.post(
            "/admin/number-mute",
            data={"phone_number_id": settings.kapso_phone_number_id, "muted": "true"},
        )
        global_response = client.post("/admin/global", data={"muted": "true"})
        assert "Desmutar número" in number.text
        assert "El bot está apagado para todos." in global_response.text


def test_booking_followup_control_round_trip(settings):
    with TestClient(create_app(settings)) as client:
        _login(client)
        page = client.get("/admin")
        assert 'type="range"' in page.text
        assert 'min="0"' in page.text
        assert 'max="90"' in page.text
        assert '<select id="booking-followup-stepper"' in page.text
        assert 'id="global-change-dialog"' in page.text
        assert 'class="global-save" type="button"' in page.text
        assert 'onclick="openGlobalChange(this.form)"' in page.text
        assert "htmx.ajax('POST', form.getAttribute('hx-post')" in page.text
        response = client.post(
            "/admin/booking-followup", data={"minutes": "10", "slider_step": "5"}
        )
        assert response.status_code == 200
        assert 'step="5"' in response.text
        assert "18 pasos de 5 min" in response.text
        runtime = SqliteRuntimeSettingsRepository(client.app.state.db)
        assert runtime.booking_followup_minutes(default=90) == 10

        invalid = client.post("/admin/booking-followup", data={"minutes": "91"})
        assert 'value="10"' in invalid.text


def test_appointment_reminder_control_is_global_and_supports_one_minute_testing(settings):
    with TestClient(create_app(settings)) as client:
        _login(client)
        page = client.get("/admin")
        assert "Recordatorio de cita" in page.text
        assert 'id="appointment-reminder-minutes"' in page.text
        assert 'type="number"' in page.text
        assert 'min="1"' in page.text
        assert 'max="10080"' in page.text
        response = client.post(
            "/admin/appointment-reminder-settings", data={"minutes": "2"}
        )
        assert response.status_code == 200
        assert 'value="2"' in response.text
        runtime = SqliteRuntimeSettingsRepository(client.app.state.db)
        assert runtime.appointment_reminder_minutes(default=1440) == 2
        assert "Tiempos sugeridos" in page.text
        assert "El slider" not in page.text


def test_global_changes_save_explicitly_after_modal_confirmation(settings):
    with TestClient(create_app(settings)) as client:
        _login(client)
        page = client.get("/admin")
    assert 'type="button" onclick="openGlobalChange(this.form)"' in page.text
    assert "htmx.ajax('POST', form.getAttribute('hx-post')" in page.text
    assert "form.reportValidity()" in page.text


def test_one_row_per_contact_keeps_the_most_recent_conversation():
    from datetime import UTC, datetime

    from agente.ports.channel import ConversationRow
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
    from agente.ports.channel import ConversationRow
    from agente.web.panel import one_row_per_contact

    anonymous = [
        ConversationRow("c1", None, None, None, None, "ended"),
        ConversationRow("c2", None, None, None, None, "ended"),
    ]
    rows, counts = one_row_per_contact(anonymous)
    assert len(rows) == 2
    assert counts == {"c1": 1, "c2": 1}


def test_reset_requires_a_session(settings):
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/admin/reset",
            data={"phone_number_id": "1087343774471931", "contact_phone": "+12052943796"},
        )
    assert response.status_code == 401


def test_reset_erases_the_contact_and_audits_it(settings):
    """Everything about the contact goes, in one transaction, with a trail."""
    key = ContactKey("1087343774471931", "+12052943796")
    now = datetime(2026, 8, 16, 12, tzinfo=UTC)
    app = create_app(settings)
    with TestClient(app) as client:
        messages = SqliteMessagesRepository(app.state.db)
        messages.add_inbound(key, "in-1", "hola", now)
        messages.add_outbound(key, "out-1", "buenas", now)
        SqliteMutesRepository(app.state.db).set_mute(key, now, actor="test", reason="test")
        app.state.channel = FakeChannel()
        _login(client)

        response = client.post(
            "/admin/reset",
            data={"phone_number_id": key.phone_number_id, "contact_phone": key.contact_phone},
        )
        assert response.status_code == 200
        assert messages.window(key, 10) == []
        mutes = SqliteMutesRepository(app.state.db)
        assert mutes.contact_mute(key) is None
        assert any(entry.action == "contact_purged" for entry in mutes.audit_trail())


def test_reset_on_a_contact_with_nothing_stored_is_harmless(settings):
    key = ContactKey("1087343774471931", "+12052943796")
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.channel = FakeChannel()
        _login(client)
        response = client.post(
            "/admin/reset",
            data={"phone_number_id": key.phone_number_id, "contact_phone": key.contact_phone},
        )
    assert response.status_code == 200
    assert "No había nada guardado" in response.text


def test_the_contact_row_offers_the_reset_button(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.channel = FakeChannel()
        _login(client)
        body = client.get("/admin").text
    assert "/admin/reset" in body
    assert "hx-confirm" in body
