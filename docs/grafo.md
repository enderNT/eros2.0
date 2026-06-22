# Grafo de LangGraph

Traducción del diseño al grafo de LangGraph: topología, nodos, canales del `state` y aristas condicionales. Complementa los ADRs (`docs/adr/`) y el glosario (`CONTEXT.md`).

## Canales del `state`

```python
# StateGraph(State)
messages   # Annotated[list, add_messages] — reducer nativo; al LLM va una ventana de 10
perfil     # {identidad, memoria_larga}     — lo escribe ensamblar_contexto (hidratado fresco)
ruteo      # {intencion, motivo}            — lo escribe supervisor
tarea      # {tipo, subestado, link_enviado, datos{nombre,correo,asunto}, slot_elegido}
meta       # {bot_activo, crisis, user_id, canal, handoff_reason}
salida     # texto a enviar + resultado del agente
```

La **memoria corta** es el checkpointer de LangGraph (por `thread_id`). El **perfil** se hidrata fresco desde un store propio cada turno; el checkpoint solo guarda `user_id` (ver ADR 0002).

## Nodos

| Nodo | Responsabilidad | Lee | Escribe |
|------|-----------------|-----|---------|
| `entrada` | Lee `bot_activo` del atributo de conversación (Chatwoot) + datos del canal | mensaje, Chatwoot | `meta` |
| `chequeo_crisis` | Check rápido (Haiku, salida estructurada `{crisis: bool}`) | `messages` | `meta.crisis` |
| `ensamblar_contexto` | Hidrata `perfil` del store (por `user_id`), arma ventana de 10 y el recordatorio de estado | store, `messages`, `tarea` | `perfil` |
| `supervisor` | Clasifica intención (Haiku, salida estructurada). Recibe versión recortada + `tarea` para sticky | contexto recortado | `ruteo` |
| `agente_faq` | Responde solo desde la Wiki; abstención + ofrece humano si falta | Wiki, contexto | `salida` |
| `agente_citas` | Máquina de estados; tools Calendly (disponibilidad, `POST /invitees`) | `tarea`, contexto | `tarea`, `salida` |
| `agente_conversacion` | Continúa en rol, sin tarea accionable | contexto | `salida` |
| `enviar` | Manda la respuesta al usuario (Chatwoot API) | `salida` | — |
| `persistir` | Memoria larga por eventos (si `tarea→CONFIRMADA`, escribe `citas_previas`/`ultima_cita`) | `tarea` | store |
| `handoff` | Compone mensaje (crisis o cortesía según `handoff_reason`), envía, setea `bot_activo=false` | `meta` | Chatwoot |

## Aristas condicionales (routers)

```
r_bot_activo  (tras entrada):        off → END                       | on → chequeo_crisis
r_crisis      (tras chequeo_crisis): crisis → handoff(crisis)        | no → ensamblar_contexto
r_intencion   (tras supervisor):     faq → agente_faq                | agendar → agente_citas
                                     conversacion → agente_conversacion | handoff → handoff(cortesia)
r_resultado   (tras cada agente):    resuelto → enviar               | fuera_de_alcance|pide_humano → handoff(cortesia)
```

Aristas fijas: `enviar → persistir → END` · `handoff → END` · cada `agente_* → r_resultado`.

## Flujo

```
entrada ─r_bot_activo─ off ─────────────────────────────────► END
   │ on
chequeo_crisis ─r_crisis─ crisis ──────────────► handoff ───► END
   │ no
ensamblar_contexto ──► supervisor ─r_intencion─┬─ faq ──────► agente_faq ──┐
                                               ├─ agendar ──► agente_citas ─┤
                                               ├─ conversa ─► agente_conv ──┤
                                               │                            ▼
                                               │                       r_resultado ─┬─ resuelto ──► enviar ─► persistir ─► END
                                               │                                     └─ fuera/pide_humano ─► handoff ─► END
                                               └─ handoff ─────────────────────────► handoff ─► END
```

## Notas de traducción

1. `entrada` y `chequeo_crisis` van **antes** de `ensamblar_contexto`: un mensaje con bot off o en crisis no paga el costo de hidratar perfil ni clasificar.
2. El **sticky routing no es un nodo**: vive en que `tarea` persiste en el checkpoint y el `supervisor` la recibe como contexto.
3. `agente_citas` es el único nodo "gordo" (máquina de estados interna + tools Calendly); los demás son de un solo paso.

## Máquina de estados de `agente_citas`

```
subestado: OFRECER_AUTOSERVICIO | RECOPILANDO | CONFIRMANDO | CONFIRMADA | ABANDONADA

agendar (sin tarea) ─┬─ ¿nombra slot? SÍ → RECOPILANDO (sin link)
                     └─ NO → OFRECER_AUTOSERVICIO (manda link, link_enviado=true)
OFRECER_AUTOSERVICIO ── insiste / propone / "no vi horarios" → RECOPILANDO
RECOPILANDO ── junta {nombre,correo,asunto} + resuelve slot_elegido → CONFIRMANDO
CONFIRMANDO ─┬─ "sí" → POST /invitees ─┬─ 2xx → CONFIRMADA
             │                          ├─ slot ocupado → RECOPILANDO
             │                          └─ error técnico → reintento → handoff
             └─ descarte explícito → ABANDONADA
```
El grafo gobierna las transiciones; el LLM solo redacta. Nunca se confirma sin `2xx` verificado.
