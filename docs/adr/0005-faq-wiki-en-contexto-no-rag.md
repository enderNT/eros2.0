# FAQ con Wiki en contexto, no RAG

El agente FAQ responde desde una Wiki curada a mano, cargada en contexto y cacheada con prompt caching, no con RAG / vector DB. La Wiki es markdown estático por secciones (servicios, precios, horarios, ubicaciones, modalidades, políticas, terapeutas) y es la fuente única de verdad.

Se eligió porque el corpus factual de la clínica es pequeño y estático: cabe en contexto, evita errores de retrieval/chunking, no necesita infraestructura de embeddings, y es más exacto y auditable —clave en un dominio de salud—. El agente responde únicamente desde la Wiki y se abstiene (ofreciendo Handoff) si la respuesta no está ahí.

## Consecuencias

- La Wiki se carga como capa estable del prompt de FAQ y se cachea entre todos los usuarios (el mayor ahorro de tokens).
- Si el corpus creciera a cientos de documentos o se volviera dinámico, se reconsideraría RAG.
