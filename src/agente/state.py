"""Contrato del `state` de LangGraph.

Cinco grupos de nivel superior por volatilidad/dueño (ver docs/grafo.md):
  messages · perfil · ruteo · tarea · meta  (+ salida del turno)

Los grupos tipo dict usan un reducer de merge superficial para que cada nodo
pueda devolver solo los campos que cambia, sin pisar el resto del grupo.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, TypedDict

from langgraph.graph.message import add_messages

# --- Enums del dominio -------------------------------------------------------

Intencion = Literal["faq", "agendar", "conversacion", "handoff"]
Resultado = Literal["resuelto", "fuera_de_alcance", "pide_humano"]
HandoffReason = Literal["crisis", "cortesia"]
SubestadoCita = Literal[
    "OFRECER_AUTOSERVICIO", "RECOPILANDO", "CONFIRMANDO", "CONFIRMADA", "ABANDONADA"
]


# --- Reducer de merge superficial para los grupos dict -----------------------

def merge_dict(left: Optional[dict], right: Optional[dict]) -> dict:
    """Merge superficial: el nodo devuelve solo lo que cambia."""
    if not right:
        return left or {}
    return {**(left or {}), **right}


# --- Subestructuras ----------------------------------------------------------

class Identidad(TypedDict, total=False):
    nombre: Optional[str]
    correo: Optional[str]
    canal: Optional[str]
    es_paciente: Literal["nuevo", "recurrente"]


class MemoriaLarga(TypedDict, total=False):
    citas_previas: int
    ultima_cita: Optional[str]


class Perfil(TypedDict, total=False):
    identidad: Identidad
    memoria_larga: MemoriaLarga


class Ruteo(TypedDict, total=False):
    intencion: Intencion
    motivo: str


class DatosCita(TypedDict, total=False):
    nombre: Optional[str]
    correo: Optional[str]
    asunto: Optional[str]


class Tarea(TypedDict, total=False):
    tipo: Optional[Literal["citas"]]
    subestado: Optional[SubestadoCita]
    link_enviado: bool
    datos: DatosCita
    slot_elegido: Optional[str]  # start_time concreto en UTC (ISO 8601)
    pidiendo: Optional[str]  # campo que el slot-filling está solicitando ahora


class Meta(TypedDict, total=False):
    bot_activo: bool
    crisis: bool
    user_id: str
    canal: str
    conversation_id: object  # id de la conversación en Chatwoot
    handoff_reason: Optional[HandoffReason]


class Salida(TypedDict, total=False):
    texto: Optional[str]
    resultado: Optional[Resultado]


# --- State -------------------------------------------------------------------

class State(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    perfil: Annotated[Perfil, merge_dict]
    ruteo: Annotated[Ruteo, merge_dict]
    tarea: Annotated[Tarea, merge_dict]
    meta: Annotated[Meta, merge_dict]
    salida: Annotated[Salida, merge_dict]
