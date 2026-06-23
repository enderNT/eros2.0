"""Store de memoria en Postgres.

Memoria larga administrativa (`perfil`), historial reciente (`historial`) y resumen
rodante por conversación (`conversation_summaries`). Persistencia exclusiva en Postgres.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from .config import settings

log = logging.getLogger(__name__)


class Store:
    def __init__(self, database_url: str):
        if not database_url:
            raise RuntimeError("DATABASE_URL es requerido para la memoria Postgres")
        self.database_url = database_url
        self._schema_ready = False
        with self._connect() as conn:
            self._ensure_schema(conn)

    def _connect(self):
        import psycopg

        return psycopg.connect(self.database_url)

    def _ensure_schema(self, conn) -> None:
        if self._schema_ready:
            return
        conn.execute(
            """CREATE TABLE IF NOT EXISTS perfil(
                user_id TEXT PRIMARY KEY,
                nombre TEXT,
                correo TEXT,
                es_paciente TEXT,
                citas_previas INTEGER DEFAULT 0,
                ultima_cita TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS historial(
                id BIGSERIAL PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                user_id TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                ts TIMESTAMPTZ NOT NULL DEFAULT now()
            )"""
        )
        conn.execute("ALTER TABLE historial ADD COLUMN IF NOT EXISTS user_id TEXT")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS conversation_summaries(
                conversation_id TEXT PRIMARY KEY,
                user_id TEXT,
                summary TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )"""
        )
        conn.execute("ALTER TABLE conversation_summaries ADD COLUMN IF NOT EXISTS user_id TEXT")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS recordatorios(
                id BIGSERIAL PRIMARY KEY,
                calendly_invitee_uri TEXT,
                calendly_event_uri TEXT,
                conversation_id TEXT NOT NULL,
                user_id TEXT,
                nombre TEXT,
                correo TEXT,
                slot TIMESTAMPTZ NOT NULL,
                remind_at TIMESTAMPTZ NOT NULL,
                lead_minutes INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                intentos INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                sent_at TIMESTAMPTZ,
                UNIQUE (calendly_invitee_uri, lead_minutes)
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_conv ON historial(conversation_id, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_user ON historial(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_summary_user ON conversation_summaries(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_recordatorios_due ON recordatorios(status, remind_at)")
        self._schema_ready = True

    # --- Historial (memoria corta) -------------------------------------------

    def cargar_historial(self, conversation_id: str, limite: int = 10) -> list[dict]:
        """Últimos `limite` turnos en orden cronológico."""
        with self._connect() as conn:
            self._ensure_schema(conn)
            rows = conn.execute(
                "SELECT role, content FROM historial WHERE conversation_id = %s "
                "ORDER BY id DESC LIMIT %s",
                (str(conversation_id), limite),
            ).fetchall()
        return [{"role": r, "content": c} for r, c in reversed(rows)]

    def cargar_historial_completo(self, conversation_id: str) -> list[dict]:
        with self._connect() as conn:
            self._ensure_schema(conn)
            rows = conn.execute(
                "SELECT id, role, content FROM historial WHERE conversation_id = %s ORDER BY id",
                (str(conversation_id),),
            ).fetchall()
        return [{"id": row[0], "role": row[1], "content": row[2]} for row in rows]

    def contar_historial(self, conversation_id: str) -> int:
        with self._connect() as conn:
            self._ensure_schema(conn)
            row = conn.execute(
                "SELECT COUNT(*) FROM historial WHERE conversation_id = %s",
                (str(conversation_id),),
            ).fetchone()
        return int(row[0] if row else 0)

    def agregar_turno(self, conversation_id: str, role: str, content: str, user_id: str | None = None) -> None:
        with self._connect() as conn:
            self._ensure_schema(conn)
            conn.execute(
                "INSERT INTO historial(conversation_id, user_id, role, content) VALUES(%s, %s, %s, %s)",
                (str(conversation_id), str(user_id) if user_id is not None else None, role, content),
            )

    def reemplazar_historial(self, conversation_id: str, turnos: list[dict], user_id: str | None = None) -> None:
        """Deja solo los turnos indicados para una conversación."""
        with self._connect() as conn:
            self._ensure_schema(conn)
            with conn.transaction():
                conn.execute("DELETE FROM historial WHERE conversation_id = %s", (str(conversation_id),))
                for turno in turnos:
                    conn.execute(
                        "INSERT INTO historial(conversation_id, user_id, role, content) VALUES(%s, %s, %s, %s)",
                        (
                            str(conversation_id),
                            str(user_id) if user_id is not None else None,
                            turno["role"],
                            turno["content"],
                        ),
                    )

    # --- Resumen rodante ------------------------------------------------------

    def get_resumen(self, conversation_id: str) -> str:
        with self._connect() as conn:
            self._ensure_schema(conn)
            row = conn.execute(
                "SELECT summary FROM conversation_summaries WHERE conversation_id = %s",
                (str(conversation_id),),
            ).fetchone()
        return row[0] if row else ""

    def set_resumen(self, conversation_id: str, summary: str, user_id: str | None = None) -> None:
        with self._connect() as conn:
            self._ensure_schema(conn)
            conn.execute(
                """INSERT INTO conversation_summaries(conversation_id, user_id, summary)
                   VALUES(%s, %s, %s)
                   ON CONFLICT(conversation_id) DO UPDATE SET
                     user_id = excluded.user_id,
                     summary = excluded.summary,
                     updated_at = now()""",
                (str(conversation_id), str(user_id) if user_id is not None else None, summary),
            )

    # --- Perfil (memoria larga administrativa) -------------------------------

    def get_perfil(self, user_id: str) -> dict:
        """Solo campos administrativos; no contenido clínico."""
        with self._connect() as conn:
            self._ensure_schema(conn)
            row = conn.execute(
                "SELECT nombre, correo, es_paciente, citas_previas, ultima_cita "
                "FROM perfil WHERE user_id = %s",
                (str(user_id),),
            ).fetchone()
        if not row:
            return {"identidad": {}, "memoria_larga": {"citas_previas": 0, "ultima_cita": None}}
        nombre, correo, es_paciente, citas_previas, ultima_cita = row
        return {
            "identidad": {"nombre": nombre, "correo": correo, "es_paciente": es_paciente or None},
            "memoria_larga": {"citas_previas": citas_previas or 0, "ultima_cita": ultima_cita},
        }

    # --- Recordatorios de cita (cola durable) --------------------------------

    def crear_recordatorios(
        self,
        *,
        invitee_uri: str | None,
        event_uri: str | None,
        conversation_id: str,
        user_id: str | None,
        nombre: str | None,
        correo: str | None,
        slot,  # datetime aware (UTC)
        leads_minutes: list[int],
    ) -> int:
        """Inserta una fila por cada lead cuyo `remind_at` aún esté en el futuro.

        Idempotente por (invitee_uri, lead_minutes): un re-envío del webhook no
        duplica. Devuelve cuántas filas se insertaron.
        """
        from datetime import datetime, timedelta, timezone

        ahora = datetime.now(timezone.utc)
        insertadas = 0
        with self._connect() as conn:
            self._ensure_schema(conn)
            for lead in leads_minutes:
                remind_at = slot - timedelta(minutes=int(lead))
                if remind_at <= ahora:
                    continue  # ese recordatorio ya no tiene sentido (cita muy próxima)
                cur = conn.execute(
                    """INSERT INTO recordatorios(
                           calendly_invitee_uri, calendly_event_uri, conversation_id,
                           user_id, nombre, correo, slot, remind_at, lead_minutes)
                       VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (calendly_invitee_uri, lead_minutes) DO NOTHING""",
                    (
                        invitee_uri, event_uri, str(conversation_id),
                        str(user_id) if user_id is not None else None,
                        nombre, correo, slot, remind_at, int(lead),
                    ),
                )
                insertadas += cur.rowcount or 0
        return insertadas

    def reclamar_recordatorios_vencidos(self, limite: int = 20) -> list[dict]:
        """Toma atómicamente recordatorios vencidos (pending, o sending colgados >5min)
        y los marca 'sending'. FOR UPDATE SKIP LOCKED evita doble envío entre corridas."""
        with self._connect() as conn:
            self._ensure_schema(conn)
            rows = conn.execute(
                """UPDATE recordatorios SET status='sending'
                   WHERE id IN (
                       SELECT id FROM recordatorios
                       WHERE remind_at <= now()
                         AND (status='pending'
                              OR (status='sending' AND remind_at <= now() - interval '5 minutes'))
                       ORDER BY remind_at
                       LIMIT %s
                       FOR UPDATE SKIP LOCKED
                   )
                   RETURNING id, conversation_id, nombre, correo, slot, lead_minutes""",
                (limite,),
            ).fetchall()
        return [
            {
                "id": r[0], "conversation_id": r[1], "nombre": r[2],
                "correo": r[3], "slot": r[4], "lead_minutes": r[5],
            }
            for r in rows
        ]

    def marcar_recordatorio_enviado(self, rid: int) -> None:
        with self._connect() as conn:
            self._ensure_schema(conn)
            conn.execute(
                "UPDATE recordatorios SET status='sent', sent_at=now() WHERE id=%s", (rid,)
            )

    def marcar_recordatorio_fallido(self, rid: int, error: str, max_intentos: int = 5) -> None:
        """Suma un intento; vuelve a 'pending' para reintentar, o 'failed' si se agotó."""
        with self._connect() as conn:
            self._ensure_schema(conn)
            conn.execute(
                """UPDATE recordatorios
                   SET intentos = intentos + 1,
                       error = %s,
                       status = CASE WHEN intentos + 1 >= %s THEN 'failed' ELSE 'pending' END
                   WHERE id = %s""",
                (error[:300], max_intentos, rid),
            )

    def cancelar_recordatorios_por_invitee(self, invitee_uri: str) -> int:
        with self._connect() as conn:
            self._ensure_schema(conn)
            cur = conn.execute(
                """UPDATE recordatorios SET status='cancelled'
                   WHERE calendly_invitee_uri=%s AND status IN ('pending','sending')""",
                (invitee_uri,),
            )
            return cur.rowcount or 0

    def conversacion_por_correo(self, correo: str) -> dict | None:
        """Recupera conversation_id/user_id de un recordatorio previo con ese correo.
        Sirve para reagendamientos vía Calendly (el webhook no trae conversation_id)."""
        if not correo:
            return None
        with self._connect() as conn:
            self._ensure_schema(conn)
            row = conn.execute(
                """SELECT conversation_id, user_id FROM recordatorios
                   WHERE correo=%s ORDER BY created_at DESC LIMIT 1""",
                (correo,),
            ).fetchone()
        return {"conversation_id": row[0], "user_id": row[1]} if row else None

    def registrar_cita(self, user_id: str, fecha: str) -> None:
        with self._connect() as conn:
            self._ensure_schema(conn)
            conn.execute(
                """INSERT INTO perfil(user_id, citas_previas, ultima_cita) VALUES(%s, 1, %s)
                   ON CONFLICT(user_id) DO UPDATE SET
                     citas_previas = perfil.citas_previas + 1,
                     ultima_cita = excluded.ultima_cita""",
                (str(user_id), fecha),
            )


@lru_cache(maxsize=1)
def get_store() -> Store:
    return Store(settings.database_url)
