"""Store de memoria larga (T9 · ADR 0002 · V5 · V6).

SQLite propio, llaveado por user_id (ID del canal). Solo campos administrativos
—nunca contenido clínico—. Escrito de forma determinista por el grafo.
Separado del checkpointer (que es memoria corta).
"""

import logging
import os
import sqlite3
from functools import lru_cache

from .config import settings

log = logging.getLogger(__name__)


class Store:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS perfil(
                user_id TEXT PRIMARY KEY,
                nombre TEXT,
                correo TEXT,
                es_paciente TEXT,
                citas_previas INTEGER DEFAULT 0,
                ultima_cita TEXT
            )"""
        )
        self._conn.commit()

    def get_perfil(self, user_id: str) -> dict:
        """V6: hidratación fresca. Solo campos admin (V5)."""
        row = self._conn.execute(
            "SELECT nombre, correo, es_paciente, citas_previas, ultima_cita "
            "FROM perfil WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return {"identidad": {}, "memoria_larga": {"citas_previas": 0, "ultima_cita": None}}
        nombre, correo, es_paciente, citas_previas, ultima_cita = row
        return {
            "identidad": {"nombre": nombre, "correo": correo, "es_paciente": es_paciente or None},
            "memoria_larga": {"citas_previas": citas_previas or 0, "ultima_cita": ultima_cita},
        }

    def registrar_cita(self, user_id: str, fecha: str) -> None:
        """V5: incremento determinista al confirmar una cita."""
        self._conn.execute(
            """INSERT INTO perfil(user_id, citas_previas, ultima_cita) VALUES(?, 1, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 citas_previas = citas_previas + 1,
                 ultima_cita = excluded.ultima_cita""",
            (user_id, fecha),
        )
        self._conn.commit()


@lru_cache(maxsize=1)
def get_store() -> Store:
    os.makedirs(os.path.dirname(settings.store_db_path) or ".", exist_ok=True)
    return Store(settings.store_db_path)
