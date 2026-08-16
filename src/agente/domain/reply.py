"""Reply shaping for WhatsApp (SPEC §8).

The playbook tells the model to be brief; this splitter is the safety net:
at most `max_chunks` chunks, cut on paragraph boundaries, never mid-sentence,
never an empty chunk. Content is never truncated — if the reply still does
not fit, the last chunk absorbs the remainder.
"""

from __future__ import annotations

import re

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
# A sentence ends at . ! ? … when what follows starts a new sentence: a
# capital letter, an opening question/exclamation mark or a quote. This
# keeps abbreviations like 'p. m.' or 'Dr.' inside their sentence.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÜÑ¿¡«“'\"(])")


def split_reply(text: str, *, max_chunks: int = 3, chunk_chars: int = 600) -> list[str]:
    """Split a model reply into sendable chunks; [] means nothing usable."""
    text = text.strip()
    if not text or max_chunks < 1:
        return []
    if len(text) <= chunk_chars:
        return [text]
    chunks = _pack(text, chunk_chars)
    if len(chunks) > max_chunks:
        chunks = chunks[: max_chunks - 1] + ["\n\n".join(chunks[max_chunks - 1 :])]
    return chunks


def _pack(text: str, chunk_chars: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current, current_len
        if current:
            chunks.append("\n\n".join(current))
            current, current_len = [], 0

    def push(piece: str, joiner: str) -> None:
        nonlocal current_len
        join_len = len(joiner) if current else 0
        if current and current_len + join_len + len(piece) > chunk_chars:
            flush()
        current.append(piece)
        current_len += join_len + len(piece)

    for paragraph in _PARAGRAPH_BREAK.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= chunk_chars:
            push(paragraph, "\n\n")
        else:
            for sentence in _split_sentences(paragraph):
                push(sentence, " ")
    flush()
    return chunks


def _split_sentences(paragraph: str) -> list[str]:
    sentences = [part.strip() for part in _SENTENCE_BREAK.split(paragraph) if part.strip()]
    return sentences or [paragraph]
