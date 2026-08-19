# C03 — Cancelación con horas de antelación

**Ejecutar:**

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c03_cancelacion.py -q
```

**Registro:** `evals/.runs/C03-cancelacion/reporte.md` · **Código:** [`../cases/test_c03_cancelacion.py`](../cases/test_c03_cancelacion.py)

## Qué se prueba

El camino de cancelación que sí existe, entero, y si el bot promete algo que no
puede cumplir mientras tanto.

**El bot no puede cancelar.** Sus herramientas son `buscar_wiki`,
`ver_horarios`, `agendar_cita` y `escalar_a_humano`; el cliente de Calendly sólo
consulta disponibilidad y crea enlaces. La cancelación entra únicamente por el
webhook `invitee.canceled`, que dispara el paciente desde su correo.

## Precondición

La monta el caso con `preparar_cita(en_minutos=360)`: se ofrece el hueco en el
calendario, el paciente lo pide, el bot negocia hasta mandar el enlace y sólo
entonces se simula `invitee.created`. **Sin atajos**: insertar la cita en la base
directamente probaría el webhook pero no la conversación.

| Ajuste | Valor |
|---|---|
| Recordatorio de cita | 60 min |

## Pasos

1. Cita confirmada dentro de 6 horas, con su recordatorio pendiente.
2. `msg "necesito cancelar la cita de hoy"` — y se observa **qué no hace**.
3. Se lee el estado.
4. Cancelación por el camino real: `invitee.canceled` firmado.
5. Se lee el estado otra vez.

## Criterios

| # | Criterio | Esperado |
|---|---|---|
| 1 | La precondición dejó cita vigente y recordatorio pendiente | SÍ |
| 2 | Tras pedirlo por chat, la cita sigue vigente | SÍ |
| 3 | El hueco sigue ocupado en el calendario | SÍ |
| 4 | Tras `invitee.canceled` la cita queda cancelada | SÍ |
| 5 | El recordatorio pendiente desapareció | SÍ |
| 6 | El aviso de cancelación llegó al chat sin intervención humana | SÍ |
| 7 | El hueco volvió a quedar libre | SÍ |

> **En `--calendario real`, los criterios sobre la ocupación del hueco quedan informativos.** La reserva se simula por webhook, así que el hueco nunca llega a ocuparse en Calendly: responder que sí o que no sería inventarse el dato.

Métrica del juez: *No afirma haber cancelado lo que no puede cancelar* (0.9).

## Cómo leerlo

Los criterios 2 y 3 esperan `SÍ` porque describen una limitación conocida:
hablar con el bot no cancela nada. Eso no es el problema. El problema sería que
el bot **dijera** que la canceló, y de eso se encarga la métrica del juez: si
reprueba, es **bug grave** — promete un efecto que no ocurre sobre una cita real
— y hay que copiar la frase literal del informe.

El criterio 5 es el que evita el peor final posible: una cita cancelada cuyo
recordatorio sigue vivo y le llega al paciente igualmente.
