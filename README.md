# Agente — Asistente de Clínica Psicológica

Asistente conversacional (LangGraph + Anthropic SDK) que orquesta entre
conversación, FAQ y agendamiento de citas, con chequeo de crisis y handoff a
humano. Canal: Chatwoot. Agendamiento: Calendly.

Diseño: [`CONTEXT.md`](CONTEXT.md) (glosario) · [`docs/grafo.md`](docs/grafo.md)
(grafo) · [`docs/adr/`](docs/adr/) (decisiones).

> **Estado: scaffold.** El grafo, los routers, el `state` y el checkpointer
> SQLite están cableados y son ejecutables; los nodos son stubs con `TODO`
> que apuntan al diseño (LLMs, Wiki, Calendly y Chatwoot aún sin implementar).

## Estructura

```
src/agente/
  state.py        # contrato del state (messages · perfil · ruteo · tarea · meta · salida)
  graph.py        # build_graph(): nodos + aristas + checkpointer
  routers.py      # aristas condicionales (r_bot_activo, r_crisis, r_intencion, r_resultado)
  config.py       # settings desde entorno
  app.py          # FastAPI: /health + /webhook/chatwoot
  cli.py          # REPL local para probar el grafo
  nodes/
    gates.py        # entrada, chequeo_crisis
    contexto.py     # ensamblar_contexto
    supervisor.py   # supervisor (Haiku)
    agentes.py      # agente_faq, agente_conversacion
    citas.py        # agente_citas (máquina de estados)
    egress.py       # enviar, persistir, handoff
```

## Desarrollo local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env        # poner ANTHROPIC_API_KEY, etc.

python -m agente.cli        # REPL para probar el grafo
# o el servicio web:
uvicorn agente.app:app --reload
```

`MODEL_*`, `CHECKPOINT_DB_PATH`, `HISTORY_WINDOW` y las credenciales de
Chatwoot/Calendly se configuran por variables de entorno (ver `.env.example`).

## Docker / Coolify

```bash
docker build -t agente .
docker run -p 8000:8000 --env-file .env -v agente_data:/data agente
```

Para levantar el stack completo local con logger LLM:

```bash
docker compose up -d --build
```

- API: `http://127.0.0.1:8000`
- Visor de flujos LLM: `http://127.0.0.1:3101`
- Postgres queda en el servicio `llm-logs-db`; el compose inyecta
  `DATABASE_URL=postgresql://agente:agente@llm-logs-db:5432/agente_logs`.

El logger persiste la entrada textual y la respuesta textual de cada llamada
Anthropic (`messages.parse` y `messages.create`) y las agrupa por flujo de
mensaje (`flow_id = chatwoot:{message_id}`). En el visor, cada flujo muestra sus
etapas en orden: chequeo de crisis, generación de respuesta y cualquier llamada
adicional dentro de la misma etapa. Si `DATABASE_URL` está vacío, el logger queda
inactivo y la app sigue funcionando sin Postgres.

En **Coolify**:
- Desplegar desde el `Dockerfile` (expone el puerto **8000**).
- Montar un **volumen persistente en `/data`** — ahí vive el SQLite del
  checkpointer (`CHECKPOINT_DB_PATH=/data/checkpoints.sqlite`, ya por default
  en la imagen). Sin volumen, la memoria corta se pierde en cada redeploy.
- Cargar las variables de entorno del `.env.example`.
- Healthcheck: `GET /health`.
- Apuntar el webhook de Chatwoot a `POST /webhook/chatwoot`.

## Próximos pasos (rellenar stubs)

1. `chequeo_crisis` y `supervisor` → llamadas a Haiku con salida estructurada.
2. `agente_faq` → Wiki en contexto + caching; `agente_conversacion` → Opus.
3. `agente_citas` → transiciones + tools Calendly (`event_types` →
   `available_times` → `POST /invitees`).
4. `ensamblar_contexto` / `persistir` → store de memoria larga (por user_id).
5. `enviar` / `handoff` → Chatwoot API (enviar mensaje, atributo `bot_activo`).
6. `app.py` → parseo real del webhook de Chatwoot + validación de firma.


Para el caso de autismo, esta bien preguntar grado de autismo, esta bien preguntar la edad. Esta bien preguntar para estudios previos
[COMPLETAR: agrega aquí 1–3 principios propios de cómo quieres que se sienta tu
clínica. Ej: ". Habla de *criterio*, no de
pasos.]
