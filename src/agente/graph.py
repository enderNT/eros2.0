"""Construcción del grafo de LangGraph (topología en docs/grafo.md)."""

from langgraph.graph import END, START, StateGraph

from .nodes.agentes import agente_conversacion, agente_faq
from .nodes.citas import agente_citas
from .nodes.contexto import ensamblar_contexto
from .nodes.egress import enviar, handoff, persistir
from .nodes.gates import chequeo_crisis, entrada
from .nodes.supervisor import supervisor
from .routers import r_bot_activo, r_crisis, r_intencion, r_resultado
from .state import State


def build_graph(checkpointer=None):
    g = StateGraph(State)

    # Nodos
    g.add_node("entrada", entrada)
    g.add_node("chequeo_crisis", chequeo_crisis)
    g.add_node("ensamblar_contexto", ensamblar_contexto)
    g.add_node("supervisor", supervisor)
    g.add_node("agente_faq", agente_faq)
    g.add_node("agente_citas", agente_citas)
    g.add_node("agente_conversacion", agente_conversacion)
    g.add_node("enviar", enviar)
    g.add_node("persistir", persistir)
    g.add_node("handoff", handoff)

    # Aristas
    g.add_edge(START, "entrada")
    g.add_conditional_edges(
        "entrada", r_bot_activo, {"chequeo_crisis": "chequeo_crisis", END: END}
    )
    g.add_conditional_edges(
        "chequeo_crisis",
        r_crisis,
        {"ensamblar_contexto": "ensamblar_contexto", "handoff": "handoff"},
    )
    g.add_edge("ensamblar_contexto", "supervisor")
    g.add_conditional_edges(
        "supervisor",
        r_intencion,
        {
            "agente_faq": "agente_faq",
            "agente_citas": "agente_citas",
            "agente_conversacion": "agente_conversacion",
            "handoff": "handoff",
        },
    )
    for agente in ("agente_faq", "agente_citas", "agente_conversacion"):
        g.add_conditional_edges(
            agente, r_resultado, {"enviar": "enviar", "handoff": "handoff"}
        )
    g.add_edge("enviar", "persistir")
    g.add_edge("persistir", END)
    g.add_edge("handoff", END)

    return g.compile(checkpointer=checkpointer)
