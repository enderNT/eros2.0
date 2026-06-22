"""REPL local para probar el grafo de punta a punta.

Uso (tras `pip install -e .`):  python -m agente.cli
"""

import logging
import os
import sqlite3
import uuid

from langgraph.checkpoint.sqlite import SqliteSaver

from .config import settings
from .graph import build_graph


def main() -> None:
    logging.basicConfig(level=settings.log_level)

    os.makedirs(os.path.dirname(settings.checkpoint_db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(settings.checkpoint_db_path, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    graph = build_graph(saver)

    thread_id = f"cli-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    print(f"thread: {thread_id}  (Ctrl-C para salir)")

    try:
        while True:
            texto = input("tú> ").strip()
            if not texto:
                continue
            result = graph.invoke(
                {
                    "messages": [{"role": "user", "content": texto}],
                    "meta": {"user_id": "cli-user", "canal": "cli", "bot_activo": True},
                },
                config,
            )
            print("bot>", result.get("salida", {}).get("texto", "<sin texto>"))
    except (KeyboardInterrupt, EOFError):
        print("\nbye")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
