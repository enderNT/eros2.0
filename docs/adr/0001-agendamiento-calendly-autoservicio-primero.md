# Agendamiento con Calendly, autoservicio primero

El agente Citas usa la Scheduling API de Calendly (`GET /event_types` → `GET /event_type_available_times` → `POST /invitees`), no solo el link de autoservicio. El flujo es **"autoservicio primero"**: ante una intención genérica de agendar se manda el link de Calendly; solo si el usuario insiste, dice que no encontró horarios, o nombra un horario concreto, el agente captura datos (`nombre`, `correo`, `asunto`) y agenda por API.

Se eligió por reducir fricción —la mayoría de los usuarios agenda solo con el link— y reservar el costo de la captura de datos + la llamada a la API para quien realmente lo necesita.

## Consecuencias

- **Lock-in con Calendly**: requiere plan de pago y una app OAuth (o Personal Access Token para la propia organización).
- El único valor agendable es un `start_time` concreto en UTC (un Slot elegido), no una Franja; toda franja debe resolverse contra disponibilidad antes de poder reservar.
- El agente nunca confirma una cita sin un `2xx` verificado de `POST /invitees`: el grafo gobierna las transiciones, el LLM solo redacta.
- La disponibilidad se consulta en ventanas de máximo 7 días por request (límite de la API).
