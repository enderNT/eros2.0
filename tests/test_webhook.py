"""Tests del parseo del webhook de Chatwoot (T14 · V1)."""

import agente.webhook as wh_mod
from agente.webhook import parse_evento, _ya_procesado


def _clear_seen():
    """Limpia el caché de IDs procesados entre tests."""
    wh_mod._seen_ids.clear()


def test_parse_incoming():
    _clear_seen()
    p = {
        "event": "message_created",
        "message_type": "incoming",
        "id": 1001,
        "content": "hola",
        "conversation": {"id": 7, "custom_attributes": {"bot_activo": True}},
        "sender": {"id": 3, "type": "contact"},
    }
    ev = parse_evento(p)
    assert ev["conversation_id"] == 7
    assert ev["texto"] == "hola"
    assert ev["user_id"] == "3"
    assert ev["bot_activo"] is True
    assert ev["message_id"] == 1001


def test_parse_incoming_int_type():
    """message_type como entero 0 (formato nativo de Chatwoot) debe procesarse."""
    _clear_seen()
    p = {
        "event": "message_created",
        "message_type": 0,
        "id": 1002,
        "content": "hola",
        "conversation": {"id": 8},
        "sender": {"id": 4, "type": "contact"},
    }
    assert parse_evento(p) is not None


def test_parse_outgoing_ignorado():
    _clear_seen()
    assert parse_evento(
        {"event": "message_created", "message_type": "outgoing", "id": 2001, "conversation": {"id": 7}}
    ) is None


def test_parse_outgoing_int_ignorado():
    """message_type como entero 1 (saliente) debe ignorarse para evitar el bucle."""
    _clear_seen()
    assert parse_evento(
        {"event": "message_created", "message_type": 1, "id": 2002, "conversation": {"id": 7}}
    ) is None


def test_parse_otro_evento_ignorado():
    assert parse_evento({"event": "conversation_updated"}) is None


def test_v1_parse_bot_off_string():
    _clear_seen()
    p = {
        "event": "message_created",
        "message_type": "incoming",
        "id": 3001,
        "content": "x",
        "conversation": {"id": 7, "custom_attributes": {"bot_activo": "false"}},
        "sender": {"id": 3, "type": "contact"},
    }
    assert parse_evento(p)["bot_activo"] is False


def test_nota_privada_ignorada():
    """Notas privadas entre agentes no deben procesarse."""
    _clear_seen()
    assert parse_evento(
        {
            "event": "message_created",
            "message_type": "incoming",
            "id": 4001,
            "private": True,
            "content": "nota interna",
            "conversation": {"id": 7},
            "sender": {"id": 5, "type": "agent"},
        }
    ) is None


def test_sender_agent_bot_ignorado():
    """Echo del bot con message_type=0 (sender.type=agent_bot) debe ignorarse."""
    _clear_seen()
    assert parse_evento(
        {
            "event": "message_created",
            "message_type": 0,
            "id": 5001,
            "content": "respuesta del bot",
            "conversation": {"id": 7},
            "sender": {"id": 99, "type": "agent_bot"},
        }
    ) is None


def test_sender_agent_ignorado():
    _clear_seen()
    assert parse_evento(
        {
            "event": "message_created",
            "message_type": "incoming",
            "id": 5002,
            "content": "echo agente",
            "conversation": {"id": 7},
            "sender": {"id": 99, "type": "agent"},
        }
    ) is None


def test_deduplicacion_mismo_id():
    """El mismo message_id no debe procesarse dos veces."""
    _clear_seen()
    p = {
        "event": "message_created",
        "message_type": "incoming",
        "id": 6001,
        "content": "hola",
        "conversation": {"id": 7},
        "sender": {"id": 3, "type": "contact"},
    }
    assert parse_evento(p) is not None   # primera vez: procesado
    assert parse_evento(p) is None       # segunda vez: duplicado ignorado


def test_deduplicacion_sin_id_siempre_pasa():
    """Sin message_id no deduplicamos — dejamos pasar (mejor que bloquear)."""
    _clear_seen()
    p = {
        "event": "message_created",
        "message_type": "incoming",
        "content": "hola",
        "conversation": {"id": 7},
        "sender": {"id": 3, "type": "contact"},
    }
    assert parse_evento(p) is not None
    assert parse_evento(p) is not None
