# Agente — Asistente de Clínica Psicológica

Asistente conversacional para una clínica psicológica, construido con LangGraph y el SDK de Anthropic. Orquesta entre conversación, respuestas factuales (FAQ) y agendamiento de citas, con escalamiento a humano.

## Language

### Orquestación

**Supervisor**:
Nodo que clasifica la intención del mensaje del usuario (dado el contexto y el estado) y enruta al agente adecuado. Corre en un modelo rápido (Haiku) con salida estructurada.
_Avoid_: Router (úsese como descripción, no como nombre del nodo), clasificador

**Sticky routing**:
Persistencia de tarea: una tarea a medias (p.ej. una Cita en curso) sobrevive en `tarea` independientemente del ruteo de un turno. Un turno puede desviarse (p.ej. a FAQ) sin destruir la tarea; el siguiente turno la reanuda. No fuerza la ruta — el Supervisor recibe la tarea activa como contexto y puede desviarse.

**Agente**:
Nodo especializado que resuelve un tipo de tarea. Hay tres: FAQ, Citas y Conversación.
_Avoid_: Subagente

**Handoff**:
Acción de poner `bot_activo = false` en la conversación (atributo de conversación en Chatwoot), con lo que el bot se calla por completo en ese chat. Lo dispara el agente cuando la petición está fuera de alcance o el usuario pide humano. El bot no se reactiva solo; un humano cambia el valor externamente.

**Bot activo**:
Atributo de conversación (en Chatwoot) que actúa como primerísimo gate: si está en "off", el mensaje entrante se ignora por completo —ni se ensambla contexto ni llega al Supervisor—. Si no está "off", el mensaje pasa por todo el flujo.

**Chequeo de crisis**:
Guardrail de seguridad de alta prioridad evaluado antes del Supervisor. Si detecta señales de riesgo (ideación suicida, autolesión, crisis aguda), responde con recursos de crisis predefinidos y dispara Handoff inmediato. El bot nunca maneja una crisis conversacionalmente.

### Agentes

**FAQ**:
Agente que responde preguntas factuales únicamente desde la Wiki, y se abstiene si la respuesta no está ahí.
_Avoid_: Conocimiento, RAG

**Citas**:
Agente que gestiona el agendamiento. Es una máquina de estados explícita gobernada por el grafo; el LLM redacta, el grafo decide las transiciones. Agenda contra Calendly.
_Avoid_: Reservas, agendador

**Conversación**:
Agente que continúa el diálogo dentro del rol de asistente de clínica, sin tarea accionable y sin necesidad de datos factuales.

**Valoración**:
Cita de entrada al proceso de atención ($1,000 MXN): se revisa el caso de forma personalizada y se determina el tratamiento. Es el único tipo de cita que el agente agenda (el `event_type` de Calendly); las sesiones de tratamiento posteriores se definen durante la valoración.
_Avoid_: consulta inicial, primera consulta

**Autoservicio**:
Flujo en el que el usuario agenda él mismo mediante un link de Calendly, sin que el agente Citas capture datos ni llame a la API. Es la primera respuesta por defecto ante intención de agendar.

**Slot elegido**:
Un `start_time` concreto en UTC, confirmado por el usuario. Es el único valor agendable (lo que `POST /invitees` necesita). Se produce resolviendo una Franja contra la disponibilidad de Calendly.
_Avoid_: horario, fecha-hora

**Franja**:
Pista de búsqueda expresada por el usuario (p.ej. "tardes entre semana"). Alimenta la consulta de disponibilidad pero no es agendable por sí misma; debe resolverse a un Slot elegido.
_Avoid_: horario preferido

**Wiki**:
Base de conocimiento factual curada a mano, estática, que se carga en contexto (no RAG) y se cachea. Fuente única de verdad para FAQ.
_Avoid_: Base de conocimiento, corpus

### Contexto y memoria

**Perfil**:
Snapshot estructurado de quién es el usuario, estable durante una sesión: identidad (datos duros) + memoria larga resumida (administrativa, nunca contenido clínico).
_Avoid_: Cliente (úsese para la persona, no para el objeto de datos)

**Contexto conversacional**:
El historial de mensajes de la sesión más el último mensaje. Volátil, cambia cada turno.

**Estado de tarea**:
La información de la máquina de estados en curso (p.ej. de una Cita): subestado, banderas, datos recolectados. Volátil.

**Memoria corta**:
Ventana reciente del historial, persistida en Postgres por `conversation_id` y enviada verbatim al LLM.

**Resumen rodante**:
Estado conversacional efímero de turnos antiguos, persistido en Postgres por `conversation_id` y enviado como bloque del system prompt.

**Memoria larga**:
Resumen estructurado del usuario, persistido entre sesiones en un store propio (no la Memory tool de Anthropic), bajo control de la aplicación por ser datos sensibles (PII clínica).

**Recordatorio de estado**:
Mensaje de rol `system` insertado al fondo del prompt (antes del último turno) con el estado de tarea y el dato de perfil más relevante; da recency sin romper el cache del prefijo.
