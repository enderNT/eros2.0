"""Ensamblado del system prompt en capas (loop ReAct).

Orden por volatilidad, con breakpoints de caché:
  Bloque 1 ⟨caché⟩: núcleo + playbook + wiki   (estable, compartido entre hilos)
  Bloque 2 ⟨caché⟩: perfil del usuario          (por hilo)

El historial de conversación va aparte, en `messages`. No hay recordatorio de
máquina de estados: el "estado" de la charla ES el historial.
"""

import logging

from .config import settings

log = logging.getLogger(__name__)

NUCLEO = (
    "Eres el asistente virtual de Eros Neurona, una clínica de psicología y "
    "neuromodulación. Sigues las directrices del PLAYBOOK al pie de la letra y "
    "respondes datos factuales solo con la WIKI. No inventas información ni das "
    "consejo clínico. Cuando una acción requiere agendar, consultar horarios o "
    "escalar a una persona, usas las herramientas disponibles."
)


def _leer(path: str, etiqueta: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return f"<<{etiqueta} vacía — pendiente de contenido>>"


def cargar_wiki() -> str:
    return _leer(settings.wiki_path, "Wiki")


def cargar_playbook() -> str:
    return _leer(settings.playbook_path, "Playbook")


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


def construir_system(perfil: dict | None = None) -> list:
    """Bloques de system con cache_control. El primero es estable (núcleo+playbook+
    wiki) y se cachea compartido; el segundo es el perfil, por hilo."""
    base = (
        f"{NUCLEO}\n\n"
        f"=== PLAYBOOK (directrices de comportamiento) ===\n{cargar_playbook()}\n"
        f"=== FIN PLAYBOOK ===\n\n"
        f"=== WIKI (datos factuales — única fuente para precios, horarios, etc.) ===\n"
        f"{cargar_wiki()}\n=== FIN WIKI ==="
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
    return bloques
