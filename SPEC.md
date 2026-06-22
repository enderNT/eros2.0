# SPEC — Agente Clínica Psi

## §G
bot clinica psi. langgraph+anthropic. enruta conversa/faq/cita. crisis->humano. canal chatwoot, citas calendly.

## §C
- py>=3.11. langgraph. anthropic sdk (no openai).
- mem conversacional = historial postgres + resumen rodante por conversacion. mem larga = perfil postgres, determinista. NO Memory tool anthropic.
- supervisor+crisis = haiku. agentes = opus 4.8.
- citas: grafo manda transiciones, LLM solo redacta.
- faq: solo wiki en contexto + caching. NO RAG.
- PII clinica: mem larga solo admin, nunca contenido terapeutico.
- deploy docker/coolify. puerto 8000. postgres en compose.
- 1 agente por turno. sin re-ruteo intra-turno v1.
- compaction historial: resumen rodante + ventana reciente verbatim.

## §I
- I.chatwoot ! webhook entrante (message_created), enviar msg (API), atributo conversacion `bot_activo`.
- I.calendly ! GET /event_types, GET /event_type_available_times (7d max), POST /invitees (req: event_type,start_time,name,email,timezone,location.kind). OAuth/PAT. plan pago.
- I.anthropic ! messages API. haiku(supervisor,crisis) + opus(agentes). output_config.format. prompt caching.
- I.store ! postgres. perfil por user_id; historial/resumen por conversation_id. campos perfil: citas_previas,ultima_cita.
- I.wiki ! markdown curado por secciones (servicios,precios,horarios,ubicaciones,modalidades,politicas,terapeutas).

## §V
- V1 ! bot_activo==off -> msg ignorado. ningun nodo de proceso corre (corta en r_bot_activo->END).
- V2 ! crisis detectada -> recursos predef + handoff. ANTES del supervisor. sobre-escribe intencion.
- V3 ! cita nunca subestado=CONFIRMADA sin 2xx de POST /invitees.
- V4 ! faq responde SOLO desde wiki. falta -> abstencion + ofrece humano. nunca inventa.
- V5 ! mem larga solo admin (no clinico). escrita por grafo (determinista), no por modelo.
- V6 ! perfil hidratado fresco cada turno desde postgres.
- V7 ! handoff -> bot_activo=false (atributo conversacion). no se reactiva solo (humano externo).
- V8 ! supervisor salida estructurada intencion in {faq,agendar,conversacion,handoff}.
- V9 ! cada agente emite resultado in {resuelto,fuera_de_alcance,pide_humano}.
- V10 ! valor agendable = slot_elegido (start_time UTC concreto). franja se resuelve antes de reservar.
- V11 ! tarea persiste entre turnos (sticky). sobrevive desvio de 1 turno.
- V12 ! handoff disparado por agente -> 1 msg cortesia, luego bot off (mismo turno).

## §T
id|st|task|cites
T1|x|supervisor real: haiku output_config.format -> {intencion,motivo}. recibe contexto recortado + tarea (sticky)|V8,V11,I.anthropic
T2|x|chequeo_crisis real: haiku -> {crisis:bool}. si crisis set handoff_reason=crisis + texto recursos (hueco clinica)|V2,I.anthropic
T3|x|calendly client: get event_types, get available_times (7d), post invitees. auth OAuth/PAT|V3,V10,I.calendly
T4|x|agente_citas transiciones: entrada(slot?->RECOPILANDO|->OFRECER_AUTOSERVICIO), insiste->RECOPILANDO, juntar datos+resolver slot->CONFIRMANDO, si->post->CONFIRMADA, slot ocupado->RECOPILANDO, error->reintento->handoff, descarte->ABANDONADA|V3,V10,V11,I.calendly
T5|x|extraer_slot: LLM extrae start_time UTC del msg|V10,I.anthropic
T6|x|agente_faq: cargar wiki, prompt caching, regla abstencion|V4,I.wiki,I.anthropic
T7|x|agente_conversacion: opus, nucleo+perfil+ventana|V9,I.anthropic
T8|x|prompt assembly: nucleo+guardrails, bloque por nodo, perfil, recordatorio system al fondo, 2 cache breakpoints|V4
T9|x|store mem larga: postgres get/put por user_id|V5,V6,I.store
T10|x|ensamblar_contexto real: hidratar perfil + armar recordatorio estado + ventana|V6
T11|x|persistir evento: CONFIRMADA -> +1 citas_previas, set ultima_cita|V5
T12|x|chatwoot enviar: POST msg via API|I.chatwoot
T13|x|chatwoot handoff: set atributo conversacion bot_activo=false|V7,V12,I.chatwoot
T14|x|chatwoot webhook real: validar firma, filtrar message_created entrantes, leer atributo bot_activo|V1,I.chatwoot
T15|.|config calendly: event_type unico, timezone clinica fija, location.kind. OAuth setup|I.calendly
T16|.|wiki contenido: loader + archivo curado (clinica llena)|V4,I.wiki
T17|.|crisis recursos: mensaje+protocolo aprobado (clinica define)|V2

## §B
id|date|cause|fix
