"""WhatsApp reply shaping tests (SPEC §8)."""

from agente.domain.reply import split_reply


def test_blank_reply_has_no_chunks():
    assert split_reply(" \n\t ") == []


def test_short_reply_stays_intact():
    assert split_reply("Hola, ¿cómo te ayudo?") == ["Hola, ¿cómo te ayudo?"]


def test_long_reply_prefers_paragraph_boundaries():
    first = "A" * 20
    second = "B" * 20

    assert split_reply(f"{first}\n\n{second}", chunk_chars=25) == [first, second]


def test_reply_without_paragraph_breaks_splits_only_between_sentences():
    text = "Primera frase breve. Segunda frase breve. Tercera frase breve."
    chunks = split_reply(text, chunk_chars=30)

    assert chunks == ["Primera frase breve.", "Segunda frase breve.", "Tercera frase breve."]
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")


def test_reply_is_limited_to_three_nonempty_chunks_without_losing_content():
    paragraphs = [f"Párrafo {number}." for number in range(1, 6)]
    text = "\n\n".join(paragraphs)
    chunks = split_reply(text, chunk_chars=12)

    assert len(chunks) == 3
    assert all(chunks)
    assert "\n\n".join(chunks) == text
