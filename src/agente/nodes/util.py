"""Utilidades compartidas por los nodos."""

from ..config import settings
from ..state import State


def _texto(msg) -> str:
    content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
    return content if isinstance(content, str) else str(content or "")


def ultimo_texto_usuario(state: State) -> str:
    """Texto del último mensaje (lo que el usuario acaba de escribir)."""
    msgs = state.get("messages", []) or []
    return _texto(msgs[-1]) if msgs else ""


def ventana(state: State, n: int | None = None) -> list:
    """Ventana rodante de los últimos N mensajes (default: settings.history_window)."""
    n = n or settings.history_window
    msgs = state.get("messages", []) or []
    return msgs[-n:]
