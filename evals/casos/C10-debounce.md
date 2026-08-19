# C10 — Mensajes en ráfaga: tres mensajes, un turno

**Ejecutar:**

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c10_debounce.py -q
```

**Registro:** `evals/.runs/C10-debounce/reporte.md` · **Código:** [`../cases/test_c10_debounce.py`](../cases/test_c10_debounce.py)

## Qué se prueba

La gente escribe en WhatsApp partiendo la idea en tres globos. Si el sistema
contesta a cada uno, el paciente recibe tres respuestas descoordinadas y la
clínica paga tres turnos de modelo.

Es el caso más barato del conjunto y por eso va primero: si el debounce está
roto, el resto de las conversaciones se comportan de forma rara sin motivo
aparente.

## Pasos

Tres mensajes lanzados **a la vez** (con `burst`, no en secuencia — en secuencia
cada uno esperaría a la respuesta del anterior y no habría ráfaga que medir):

`"hola"` / `"quería preguntar algo"` / `"es sobre terapia de pareja"`

| Ajuste | Valor |
|---|---|
| Debounce | 4 s (el de producción) |

## Criterios

| # | Criterio | Esperado |
|---|---|---|
| 1 | Se procesó un solo turno, no tres | SÍ |
| 2 | Los tres mensajes quedaron guardados igualmente | SÍ |
| 3 | La respuesta tiene en cuenta el tercer mensaje | SÍ |
| 4 | No hubo tres respuestas separadas | SÍ |

## Cómo leerlo

El criterio que manda es el **1**, y se mide contando `turn_id` distintos en
`llm_trace`: es el dato duro, no una impresión sobre la respuesta.

El criterio 4 es más débil a propósito: una respuesta larga se trocea por
longitud antes de enviarse, así que ver dos o tres mensajes de salida no prueba
que se procesaran tres turnos. Por eso está el 1.

El criterio 2 vigila lo contrario del debounce: agrupar para responder no puede
significar perder mensajes. Los tres tienen que estar guardados.
