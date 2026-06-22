"""Persistencia de llamadas LLM en Postgres.

El logger es deliberadamente no crítico: si Postgres no está configurado o falla,
la conversación debe continuar. Esto permite usarlo en Docker sin afectar tests ni
ejecución local mínima.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from .config import settings

log = logging.getLogger(__name__)

_MAX_TEXT_CHARS = 200_000


def _truncate(text: str) -> str:
    if len(text) <= _MAX_TEXT_CHARS:
        return text
    return text[:_MAX_TEXT_CHARS] + "\n[truncado]"


def _safe_json(value: Any) -> Any:
    """Convierte objetos del SDK en estructuras JSON simples."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _safe_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json(v) for v in value]
    if hasattr(value, "model_dump"):
        try:
            return _safe_json(value.model_dump())
        except Exception:  # noqa: BLE001
            pass
    if hasattr(value, "__dict__"):
        data = {
            k: v
            for k, v in vars(value).items()
            if not k.startswith("_") and isinstance(v, (str, int, float, bool, dict, list, tuple, type(None)))
        }
        if data:
            return _safe_json(data)
    return str(value)


def _json_text(value: Any) -> str:
    return json.dumps(_safe_json(value), ensure_ascii=False, indent=2, sort_keys=True)


def render_data_text(value: Any) -> str:
    return _truncate(_json_text(value))


def _block_to_text(block: Any) -> str:
    if isinstance(block, str):
        return block
    if isinstance(block, dict):
        kind = block.get("type")
        if kind == "text":
            return str(block.get("text", ""))
        if kind == "tool_result":
            return f"[tool_result {block.get('tool_use_id', '')}]\n{block.get('content', '')}"
        if kind == "tool_use":
            return f"[tool_use {block.get('name', '')}]\n{_json_text(block.get('input', {}))}"
        return _json_text(block)

    kind = getattr(block, "type", None)
    if kind == "text":
        return str(getattr(block, "text", ""))
    if kind == "tool_use":
        name = getattr(block, "name", "")
        inp = getattr(block, "input", {})
        return f"[tool_use {name}]\n{_json_text(inp)}"
    if kind == "tool_result":
        return f"[tool_result {getattr(block, 'tool_use_id', '')}]\n{getattr(block, 'content', '')}"
    return _json_text(block)


def content_to_text(content: Any) -> str:
    """Representación textual de contenido Anthropic o mensajes internos."""
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        return "\n\n".join(part for part in (_block_to_text(b).strip() for b in content) if part)
    return _block_to_text(content)


def render_llm_request(system: Any = None, messages: list[dict] | None = None) -> str:
    sections: list[str] = []
    if system:
        sections.append("SYSTEM\n" + content_to_text(system))
    if messages:
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            lines.append(f"[{role}]\n{content_to_text(msg.get('content', ''))}")
        sections.append("MESSAGES\n" + "\n\n".join(lines))
    return _truncate("\n\n".join(sections).strip())


def render_llm_response(resp: Any) -> str:
    parsed = getattr(resp, "parsed_output", None)
    if parsed is not None:
        return _truncate(_json_text(parsed))
    content = getattr(resp, "content", None)
    if content is not None:
        return _truncate(content_to_text(content).strip())
    return _truncate(_json_text(resp))


class LlmCallLogger:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self._schema_ready = False

    @property
    def enabled(self) -> bool:
        return bool(self.database_url)

    def _connect(self):
        import psycopg

        return psycopg.connect(self.database_url, autocommit=True)

    def _ensure_schema(self, conn) -> None:
        if self._schema_ready:
            return
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_calls(
                id BIGSERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                provider TEXT NOT NULL,
                operation TEXT NOT NULL,
                model TEXT,
                status TEXT NOT NULL,
                conversation_id TEXT,
                flow_id TEXT,
                message_id TEXT,
                stage TEXT,
                stage_label TEXT,
                stage_order INTEGER DEFAULT 0,
                call_order INTEGER DEFAULT 0,
                request_text TEXT NOT NULL,
                response_text TEXT,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb
            )
            """
        )
        for column in (
            "flow_id TEXT",
            "message_id TEXT",
            "stage TEXT",
            "stage_label TEXT",
            "stage_order INTEGER DEFAULT 0",
            "call_order INTEGER DEFAULT 0",
        ):
            conn.execute(f"ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS {column}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_created_at ON llm_calls(created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_conversation ON llm_calls(conversation_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_flow ON llm_calls(flow_id, stage_order, call_order, id)")
        self._schema_ready = True

    def record(
        self,
        *,
        provider: str,
        operation: str,
        model: str | None,
        request_text: str,
        response_text: str | None,
        status: str = "ok",
        conversation_id: str | None = None,
        flow_id: str | None = None,
        message_id: str | None = None,
        stage: str | None = None,
        stage_label: str | None = None,
        stage_order: int = 0,
        call_order: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            return
        try:
            with self._connect() as conn:
                self._ensure_schema(conn)
                conn.execute(
                    """
                    INSERT INTO llm_calls(
                        provider, operation, model, status, conversation_id,
                        flow_id, message_id, stage, stage_label, stage_order, call_order,
                        request_text, response_text, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        provider,
                        operation,
                        model,
                        status,
                        str(conversation_id) if conversation_id is not None else None,
                        str(flow_id) if flow_id is not None else None,
                        str(message_id) if message_id is not None else None,
                        stage,
                        stage_label,
                        int(stage_order or 0),
                        int(call_order or 0),
                        _truncate(request_text or ""),
                        _truncate(response_text) if response_text is not None else None,
                        json.dumps(_safe_json(metadata or {}), ensure_ascii=False),
                    ),
                )
        except Exception as e:  # noqa: BLE001
            log.warning("llm logger: no se pudo persistir llamada: %s", e)

    def list_flows(self, limit: int = 100, query: str = "") -> list[dict]:
        if not self.enabled:
            return []
        limit = max(1, min(int(limit or 100), 500))
        query = (query or "").strip()
        try:
            import psycopg.rows

            with self._connect() as conn:
                self._ensure_schema(conn)
                with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                    params: list[Any] = []
                    where = ""
                    if query:
                        pattern = f"%{query}%"
                        where = """
                            WHERE provider ILIKE %s
                               OR operation ILIKE %s
                               OR model ILIKE %s
                               OR status ILIKE %s
                               OR conversation_id ILIKE %s
                               OR flow_id ILIKE %s
                               OR message_id ILIKE %s
                               OR request_text ILIKE %s
                               OR response_text ILIKE %s
                        """
                        params = [pattern] * 9
                    cur.execute(
                        f"""
                        WITH keyed AS (
                            SELECT *,
                                   COALESCE(flow_id, 'legacy:' || id::text) AS flow_key
                            FROM llm_calls
                        ),
                        matched_flows AS (
                            SELECT DISTINCT flow_key
                            FROM keyed
                            {where}
                        ),
                        scoped AS (
                            SELECT k.*
                            FROM keyed k
                            JOIN matched_flows m ON m.flow_key = k.flow_key
                        )
                        SELECT flow_key AS flow_id,
                               MIN(created_at) AS first_created_at,
                               MAX(created_at) AS last_created_at,
                               COUNT(*)::int AS call_count,
                               MAX(conversation_id) AS conversation_id,
                               MAX(message_id) AS message_id,
                               BOOL_OR(status = 'error') AS has_error,
                               STRING_AGG(DISTINCT model, ', ' ORDER BY model) AS models,
                               (ARRAY_AGG(LEFT(request_text, 240) ORDER BY created_at, id))[1] AS preview_text
                        FROM scoped
                        GROUP BY flow_key
                        ORDER BY last_created_at DESC
                        LIMIT %s
                        """,
                        (*params, limit),
                    )
                    rows = cur.fetchall()
            out = []
            for row in rows:
                item = dict(row)
                item["first_created_at"] = item["first_created_at"].isoformat()
                item["last_created_at"] = item["last_created_at"].isoformat()
                out.append(item)
            return out
        except Exception as e:  # noqa: BLE001
            log.warning("llm logger: no se pudieron leer flujos: %s", e)
            return []

    def get_flow(self, flow_id: str) -> dict | None:
        if not self.enabled or not flow_id:
            return None
        try:
            import psycopg.rows

            with self._connect() as conn:
                self._ensure_schema(conn)
                with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                    cur.execute(
                        """
                        WITH keyed AS (
                            SELECT *,
                                   COALESCE(flow_id, 'legacy:' || id::text) AS flow_key
                            FROM llm_calls
                        )
                        SELECT id, created_at, provider, operation, model, status,
                               conversation_id, flow_key AS flow_id, message_id,
                               stage, stage_label, stage_order, call_order,
                               request_text, response_text, metadata
                        FROM keyed
                        WHERE flow_key = %s
                        ORDER BY stage_order, call_order, created_at, id
                        """,
                        (flow_id,),
                    )
                    rows = cur.fetchall()
            if not rows:
                return None

            calls = []
            for row in rows:
                item = dict(row)
                item["created_at"] = item["created_at"].isoformat()
                calls.append(item)

            stages_by_key: dict[str, dict] = {}
            for call in calls:
                stage_key = call.get("stage") or call["operation"] or "llm"
                stage = stages_by_key.setdefault(
                    stage_key,
                    {
                        "key": stage_key,
                        "label": call.get("stage_label") or _stage_label(stage_key, call.get("model")),
                        "order": call.get("stage_order") or 0,
                        "calls": [],
                    },
                )
                stage["calls"].append(call)

            stages = sorted(stages_by_key.values(), key=lambda s: (s["order"], s["key"]))
            first = calls[0]
            last = calls[-1]
            return {
                "flow_id": flow_id,
                "conversation_id": first.get("conversation_id"),
                "message_id": first.get("message_id"),
                "first_created_at": first["created_at"],
                "last_created_at": last["created_at"],
                "call_count": len(calls),
                "status": "error" if any(c["status"] == "error" for c in calls) else "ok",
                "stages": stages,
            }
        except Exception as e:  # noqa: BLE001
            log.warning("llm logger: no se pudo leer flujo: %s", e)
            return None

    def list_calls(self, limit: int = 100, query: str = "") -> list[dict]:
        if not self.enabled:
            return []
        limit = max(1, min(int(limit or 100), 500))
        query = (query or "").strip()
        try:
            import psycopg.rows

            with self._connect() as conn:
                self._ensure_schema(conn)
                with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                    if query:
                        pattern = f"%{query}%"
                        cur.execute(
                            """
                            SELECT id, created_at, provider, operation, model, status,
                                   conversation_id, request_text, response_text, metadata
                            FROM llm_calls
                            WHERE provider ILIKE %s
                               OR operation ILIKE %s
                               OR model ILIKE %s
                               OR status ILIKE %s
                               OR conversation_id ILIKE %s
                               OR request_text ILIKE %s
                               OR response_text ILIKE %s
                            ORDER BY created_at DESC, id DESC
                            LIMIT %s
                            """,
                            (pattern, pattern, pattern, pattern, pattern, pattern, pattern, limit),
                        )
                    else:
                        cur.execute(
                            """
                            SELECT id, created_at, provider, operation, model, status,
                                   conversation_id, request_text, response_text, metadata
                            FROM llm_calls
                            ORDER BY created_at DESC, id DESC
                            LIMIT %s
                            """,
                            (limit,),
                        )
                    rows = cur.fetchall()
            out = []
            for row in rows:
                item = dict(row)
                item["created_at"] = item["created_at"].isoformat()
                out.append(item)
            return out
        except Exception as e:  # noqa: BLE001
            log.warning("llm logger: no se pudieron leer logs: %s", e)
            return []


@lru_cache(maxsize=1)
def get_llm_logger() -> LlmCallLogger:
    return LlmCallLogger(settings.database_url)


def _stage_label(stage: str, model: str | None) -> str:
    if stage == "crisis_check":
        return "Chequeo de crisis"
    if stage == "memory_read":
        return "Lectura de memoria"
    if stage == "memory_write":
        return "Escritura de memoria"
    if stage == "history_persist":
        return "Persistencia de historial"
    if stage == "long_memory_write":
        return "Escritura de memoria larga"
    if stage == "agent_response":
        return "Generacion de respuesta"
    if model:
        return f"Llamada LLM {model}"
    return "Llamada LLM"
