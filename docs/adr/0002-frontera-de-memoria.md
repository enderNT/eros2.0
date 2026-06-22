# Frontera de memoria

La memoria corta es la ventana reciente de `historial` en Postgres, llaveada por `conversation_id`. El perfil del usuario se hidrata fresco desde el mismo store en cada turno, para que la memoria larga siempre refleje el dato actualizado y no se duplique la PII.

Los turnos antiguos se compactan en un resumen rodante por conversación. Ese resumen captura solo estado conversacional efímero y se inyecta como bloque del system prompt; los turnos recientes permanecen verbatim.

La memoria larga administrativa es un store propio en Postgres, llaveado por el ID del canal (p.ej. el número de WhatsApp), escrito de forma **determinista por la aplicación** ante eventos (p.ej. `citas_previas` / `ultima_cita` al agendar), nunca por el modelo.

Se descartó la Memory tool de Anthropic para mantener control total sobre qué PII clínica se persiste y garantizar el scoping por usuario. La memoria larga excluye deliberadamente contenido terapéutico; solo guarda datos administrativos.
