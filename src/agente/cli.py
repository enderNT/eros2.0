"""REPL local para probar el agente de punta a punta (sin Chatwoot).

Uso (tras `pip install -e .`):  python -m agente.cli
"""

import logging
import uuid

from .agent import responder
from .config import settings
from .llm import detectar_crisis
from .store import get_store


def main() -> None:
    logging.basicConfig(level=settings.log_level)
    store = get_store()
    conv = f"cli-{uuid.uuid4().hex[:8]}"
    user = "cli-user"
    print(f"conversación: {conv}  (Ctrl-C para salir)")

    try:
        while True:
            texto = input("tú> ").strip()
            if not texto:
                continue

            if detectar_crisis(texto):
                print("bot>", settings.crisis_message, "[escalado]")
                continue

            perfil = store.get_perfil(user)
            historial = store.cargar_historial(conv, settings.history_window)
            historial.append({"role": "user", "content": texto})
            ctx = {"conversation_id": conv, "user_id": user}
            resp = responder(historial, perfil, ctx)

            store.agregar_turno(conv, "user", texto)
            store.agregar_turno(conv, "assistant", resp)
            print("bot>", resp, "[escalado]" if ctx.get("escalado") else "")
    except (KeyboardInterrupt, EOFError):
        print("\nbye")


if __name__ == "__main__":
    main()
