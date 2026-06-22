"""Loop del agente (ReAct con herramientas).

Una sola función pública, `responder()`: recibe el historial + perfil + contexto del
canal, corre el ciclo modelo↔herramientas hasta una respuesta de texto (o tope), y
devuelve el texto final. Los turnos de herramienta son efímeros: NO se persisten; lo
que se guarda como memoria es solo el turno final del asistente (lo hace el caller).
"""

import logging

from .config import settings
from .llm import get_client
from .prompt import construir_system
from .tools import TOOLS, ejecutar_tool

log = logging.getLogger(__name__)

_FALLBACK = "Estoy teniendo un problema técnico en este momento. ¿Quieres que te conecte con una persona del equipo?"


def _texto_de(content) -> str:
    """Concatena los bloques de texto de una respuesta del modelo."""
    return "".join(b.text for b in content if getattr(b, "type", None) == "text").strip()


def _log_envio(system_blocks, messages) -> None:
    if not log.isEnabledFor(logging.DEBUG):
        return
    sizes = " | ".join(f"#{i}:{len(b.get('text', ''))}c" for i, b in enumerate(system_blocks))
    conv = "\n".join(
        f"    [{m['role']}] {str(m['content'])[:300]}"
        for m in messages
        if isinstance(m.get("content"), str)
    )
    log.debug("LLM ← system(%s)\n  messages(%d):\n%s", sizes, len(messages), conv)


def responder(historial: list, perfil: dict, ctx: dict) -> str:
    """Ejecuta el loop y devuelve el texto de respuesta para el usuario.

    historial: lista de {role: 'user'|'assistant', content: str} (ventana ya recortada).
    perfil:    dict de store.get_perfil (se inyecta al system).
    ctx:       {conversation_id, user_id, ...} para las herramientas; se muta in-place
               (p.ej. ctx['escalado']=True si se llamó escalar_a_humano).
    """
    client = get_client()
    if client is None:
        log.warning("responder: sin ANTHROPIC_API_KEY → fallback")
        return _FALLBACK

    system_blocks = construir_system(perfil)
    # Copia mutable del historial: aquí sí agregamos turnos de herramienta (efímeros).
    messages: list = [dict(m) for m in historial]
    _log_envio(system_blocks, messages)

    for vuelta in range(settings.max_iteraciones):
        try:
            resp = client.messages.create(
                model=settings.model_agente,
                max_tokens=1024,
                system=system_blocks,
                tools=TOOLS,
                messages=messages,
            )
        except Exception as e:  # noqa: BLE001
            log.error("responder: messages.create falló (vuelta %d): %s", vuelta, e)
            return _FALLBACK

        if resp.stop_reason != "tool_use":
            texto = _texto_de(resp.content)
            log.debug("LLM → %s", texto[:300])
            return texto or _FALLBACK

        # Hay tool_use: registrar el turno del asistente y ejecutar cada herramienta.
        messages.append({"role": "assistant", "content": resp.content})
        resultados = []
        for bloque in resp.content:
            if getattr(bloque, "type", None) == "tool_use":
                log.info("tool → %s(%s)", bloque.name, bloque.input)
                salida = ejecutar_tool(bloque.name, bloque.input, ctx)
                resultados.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": bloque.id,
                        "content": salida,
                    }
                )
        messages.append({"role": "user", "content": resultados})

    log.warning("responder: alcanzó el tope de %d iteraciones", settings.max_iteraciones)
    return _FALLBACK
