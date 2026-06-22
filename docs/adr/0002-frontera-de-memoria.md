# Frontera de memoria

La memoria corta es el `state`/checkpoint de LangGraph (nativo, por `thread_id`). El perfil del usuario se hidrata fresco desde un store propio en cada turno y **no** se persiste en el checkpoint —este solo guarda `user_id` como referencia—, para que la memoria larga siempre refleje el store actualizado y no se duplique la PII.

La memoria larga es un store propio, llaveado por el ID del canal (p.ej. el número de WhatsApp), escrito de forma **determinista por el grafo** ante eventos (p.ej. `citas_previas` / `ultima_cita` al llegar a `CONFIRMADA`), nunca por el modelo.

Se descartó la Memory tool de Anthropic para mantener control total sobre qué PII clínica se persiste y garantizar el scoping por usuario. La memoria larga excluye deliberadamente contenido terapéutico; solo guarda datos administrativos.
