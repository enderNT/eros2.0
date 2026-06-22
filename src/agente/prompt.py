"""Ensamblado del prompt en capas (T8 · docs/grafo.md).

Orden por volatilidad con 2 breakpoints de cache:
  [system] Capa1 núcleo+guardrails + Capa2 bloque de nodo  ⟨cache #1: compartido⟩
           Capa3 perfil                                     ⟨cache #2: por hilo⟩
  [messages] ventana + recordatorio de estado (role:system al fondo)
"""

from .nodes.util import ventana

NUCLEO = (
    "Eres el asistente virtual de una clínica psicológica. Hablas con calidez y respeto. "
    "Nunca das consejo clínico, diagnóstico ni interpretación terapéutica. "
    "Nunca inventas información (precios, horarios, datos): si no la tienes, lo dices y ofreces "
    "ayuda humana. Si la persona expresa una situación de riesgo, no la manejas tú: se escala a "
    "un humano. Te limitas a tu rol: informar, agendar y acompañar la conversación."
)


def render_perfil(perfil: dict) -> str:
    ident = (perfil or {}).get("identidad", {})
    mem = (perfil or {}).get("memoria_larga", {})
    return (
        "PERFIL DEL USUARIO:\n"
        f"- Nombre: {ident.get('nombre') or 'desconocido'}\n"
        f"- Tipo: {ident.get('es_paciente') or 'n/d'}\n"
        f"- Citas previas: {mem.get('citas_previas', 0)}\n"
        f"- Última cita: {mem.get('ultima_cita') or 'ninguna'}"
    )


def render_recordatorio(state: dict) -> str:
    tarea = state.get("tarea", {})
    if tarea.get("tipo") == "citas" and tarea.get("subestado") not in (
        None,
        "CONFIRMADA",
        "ABANDONADA",
    ):
        d = tarea.get("datos", {})
        return (
            f"ESTADO DE LA TAREA: cita en curso (subestado={tarea.get('subestado')}). "
            f"Datos: nombre={d.get('nombre') or '-'}, correo={d.get('correo') or '-'}, "
            f"asunto={d.get('asunto') or '-'}, slot={tarea.get('slot_elegido') or '-'}."
        )
    return "ESTADO DE LA TAREA: ninguna en curso."


def _to_api(msgs: list) -> list:
    out = []
    for m in msgs:
        if isinstance(m, dict):
            role, content = m.get("role", "user"), m.get("content", "")
        else:
            role = "assistant" if getattr(m, "type", "") == "ai" else "user"
            content = getattr(m, "content", "")
        out.append({"role": role, "content": content})
    return out


def construir_prompt(state: dict, bloque_nodo: str, *, incluir_perfil: bool = True) -> dict:
    """Devuelve {system: [...bloques con cache_control...], messages: [...]}"""
    system_blocks = [
        {
            "type": "text",
            "text": NUCLEO + "\n\n" + bloque_nodo,
            "cache_control": {"type": "ephemeral"},  # breakpoint #1 (compartido)
        }
    ]
    if incluir_perfil:
        system_blocks.append(
            {
                "type": "text",
                "text": render_perfil(state.get("perfil", {})),
                "cache_control": {"type": "ephemeral"},  # breakpoint #2 (por hilo)
            }
        )
    messages = _to_api(ventana(state))
    # Recordatorio de estado al fondo, como <system-reminder> dentro del turno del usuario.
    # (No usamos role:"system" en messages: es beta/model-gated y rompe en modelos que no
    #  lo soportan — "role 'system' is not supported on this model".)
    reminder = f"<system-reminder>\n{render_recordatorio(state)}\n</system-reminder>"
    if messages and messages[-1]["role"] == "user":
        messages[-1] = {"role": "user", "content": f"{messages[-1]['content']}\n\n{reminder}"}
    else:
        messages.append({"role": "user", "content": reminder})
    return {"system": system_blocks, "messages": messages}
