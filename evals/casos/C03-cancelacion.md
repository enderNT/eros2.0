# C03 — Cancelación con horas de antelación, hecha por el bot

**Ejecutar:**

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c03_cancelacion.py -q
```

**Registro:** `evals/.runs/C03-cancelacion/reporte.md` · **Código:** [`../cases/test_c03_cancelacion.py`](../cases/test_c03_cancelacion.py)

## Qué se prueba

Que cancelar sea trabajo del asistente y no del paciente — y que, siendo la
primera acción irreversible que el bot puede tomar sobre una cita real, exija
un sí explícito antes de hacerla.

Antes este caso medía lo contrario: que el bot **no prometiera** cancelar lo que
no podía cancelar, porque la cancelación sólo entraba por el correo de Calendly.

## Precondición

Cita confirmada con `preparar_cita_directa` a 6 horas, recordatorio a 60 minutos.

## Pasos

1. `msg "necesito cancelar la cita de hoy"` — y se comprueba que **no** cancela todavía.
2. `msg "sí, confírmalo, cancélala por favor"`
3. Se lee el estado.

## Criterios

| # | Criterio | Esperado |
|---|---|---|
| 0 | La cita de la precondición la reservó el propio sistema, sin enlace | SÍ |
| 1 | La precondición dejó cita vigente y recordatorio pendiente | SÍ |
| 2 | Con el primer mensaje todavía NO cancela: pide confirmación | SÍ |
| 3 | Confirmada, la cita queda cancelada | SÍ |
| 4 | El recordatorio pendiente desapareció | SÍ |
| 5 | El hueco volvió a quedar libre en el calendario | SÍ |
| 6 | El bot dijo en el chat que la cita quedó cancelada | SÍ |

Métrica del juez: *Pide confirmación antes de cancelar* (0.8).

## Cómo leerlo

Los criterios 2 y 3 tiran en direcciones opuestas a propósito, y ese es el
caso entero. Un bot que cancela con el primer mensaje aprueba el 3 y reprueba el
2 — y eso es **peor** que no saber cancelar, porque borra citas reales de gente
que sólo estaba dudando. C13 prueba justo ese escenario ambiguo.

El criterio 6 parece menor y no lo es: cancelar sin decirlo deja al paciente
creyendo que sigue teniendo cita.
