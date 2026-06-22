"""Ensamblado del system prompt en capas (loop ReAct).

Orden por volatilidad, con breakpoints de caché:
  Bloque 1 ⟨caché⟩: núcleo + playbook              (estable)
  Bloque 2 ⟨caché⟩: perfil del usuario             (por hilo)
  Bloque 3 ⟨caché⟩: resumen de conversación previa (por hilo)

La WIKI ya NO va en el system: se consulta por secciones con la herramienta
`buscar_wiki` (tools.py), para no cargar el contexto con datos que crecen.
El historial reciente va aparte, en `messages`; lo viejo se conserva como resumen
rodante.
"""

import logging

from .config import settings

log = logging.getLogger(__name__)

NUCLEO = (
    "Eres el asistente virtual de Eros Neurona, una clínica de psicología y "
    "neuromodulación. Sigues las directrices del PLAYBOOK al pie de la letra. "
    "Para CUALQUIER dato factual (precios, horarios, servicios, ubicación, "
    "políticas) consultas la herramienta `buscar_wiki` y nunca lo inventas. "
    "Para agendar, ver horarios o escalar a una persona usas las demás herramientas."
)


def cargar_playbook() -> str:
    try:
        with open(settings.playbook_path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return "<<Playbook vacío — pendiente de contenido>>"


def render_perfil(perfil: dict) -> str:
    ident = (perfil or {}).get("identidad", {})
    mem = (perfil or {}).get("memoria_larga", {})
    return (
        "PERFIL DEL USUARIO (datos administrativos, no clínicos):\n"
        f"- Nombre: {ident.get('nombre') or 'desconocido'}\n"
        f"- Correo: {ident.get('correo') or 'desconocido'}\n"
        f"- Tipo: {ident.get('es_paciente') or 'n/d'}\n"
        f"- Citas previas: {mem.get('citas_previas', 0)}\n"
        f"- Última cita: {mem.get('ultima_cita') or 'ninguna'}"
    )


def render_resumen_conversacion(resumen: str) -> str:
    return (
        "RESUMEN DE CONVERSACIÓN PREVIA (estado conversacional efímero; "
        "no repetir datos administrativos del perfil):\n"
        f"{resumen.strip()}"
    )


def construir_system(perfil: dict | None = None, resumen_conversacion: str | None = None) -> list:
    """Bloques de system con cache_control. El primero es estable (núcleo+playbook)
    y se cachea compartido; los siguientes son perfil y resumen, por hilo. La wiki
    NO va aquí: se consulta con buscar_wiki."""
    base = (
        f"{NUCLEO}\n\n"
        f"=== PLAYBOOK (directrices de comportamiento) ===\n{cargar_playbook()}\n"
        f"=== FIN PLAYBOOK ==="
    )
    bloques = [
        {"type": "text", "text": base, "cache_control": {"type": "ephemeral"}}
    ]
    if perfil is not None:
        bloques.append(
            {
                "type": "text",
                "text": render_perfil(perfil),
                "cache_control": {"type": "ephemeral"},
            }
        )
    if resumen_conversacion:
        bloques.append(
            {
                "type": "text",
                "text": render_resumen_conversacion(resumen_conversacion),
                "cache_control": {"type": "ephemeral"},
            }
        )
    return bloques
