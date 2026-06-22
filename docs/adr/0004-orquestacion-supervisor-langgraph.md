# Orquestación: Supervisor + agentes en LangGraph

La orquestación es un Supervisor (LLM en Haiku, con salida estructurada `{ intencion, motivo }`) que enruta a agentes especializados (FAQ, Citas, Conversación) en un grafo de LangGraph, en vez de un solo agente con tools.

"Sticky routing" se implementa como **persistencia de tarea**: la tarea activa vive en el `state` (`tarea`) y sobrevive a desvíos de un turno; el Supervisor la recibe como contexto pero puede desviarse sin destruirla.

Se eligió por control, observabilidad y para poder forzar la máquina de estados determinista de Citas (el grafo gobierna las transiciones, el LLM solo redacta). El costo es un LLM call extra de clasificación por turno, mitigado usando un modelo rápido (Haiku) para el Supervisor.

## Consecuencias

- Cada nodo arma su propio prefijo de prompt y se cachea por separado.
- Un agente por turno; sin re-enrutamiento intra-turno en v1.
- Cada agente emite `resultado ∈ {resuelto, fuera_de_alcance, pide_humano}`; el grafo enruta de forma determinista sin evaluador central.
