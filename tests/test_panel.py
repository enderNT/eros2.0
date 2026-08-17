from datetime import UTC, datetime

from fastapi.testclient import TestClient

from agente.adapters.store.mutes import SqliteMutesRepository
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
        assert "Activar bot" in global_response.text


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
