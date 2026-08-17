from datetime import UTC, datetime

import pytest

from agente.domain.contacts import ContactKey
from agente.tools.escalar_a_humano import escalar_a_humano


@pytest.mark.asyncio
async def test_escalation_mutes_and_audits(mutes):
    key = ContactKey("1087343774471931", "+12052943796")
    result = await escalar_a_humano(mutes, key, "solicitud", datetime(2026, 8, 16, tzinfo=UTC))
    assert mutes.is_bot_muted(key, datetime(2026, 8, 16, tzinfo=UTC))
    assert "seguimiento" in result
