# C09 — "Quiero cambiar mi cita": que mover no signifique duplicar

**Ejecutar:**

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c09_doble_reserva.py -q
```

**Registro:** `evals/.runs/C09-doble-reserva/reporte.md` · **Código:** [`../cases/test_c09_doble_reserva.py`](../cases/test_c09_doble_reserva.py)

## Qué se prueba

Que mover una cita la **mueva**, en vez de crear una segunda y dejar viva la
primera.

Este caso cambió de signo. Cuando el bot sólo sabía mandar enlaces, documentaba
el hueco: esperaba dos citas vigentes, porque no había forma de soltar la vieja.
Con `book`/`cancel` en el puerto de calendario, reagendar es cancelar y volver a
reservar, y el caso exige lo contrario.

## Precondición

Una cita confirmada con `preparar_cita_directa`, recordatorio a 60 minutos.

## Pasos

1. Cita confirmada.
2. `msg "puedo mover mi cita para otro día?"`
3. Se acepta el horario nuevo, hasta tres turnos.
4. Se lee el estado.

## Criterios

| # | Criterio | Esperado |
|---|---|---|
| 0 | La cita de la precondición la reservó el propio sistema, sin enlace | SÍ |
| 1 | Quedó exactamente una cita vigente | SÍ |
| 2 | La cita vigente ya no es la del horario original | SÍ |
| 3 | Hay un solo recordatorio pendiente | SÍ |
| 4 | El hueco viejo volvió a quedar libre | SÍ |

> **En `--calendario real`, el criterio 4 queda informativo** mientras la reserva se siga simulando por webhook: el hueco nunca llega a ocuparse en Calendly.

Métrica del juez: *Confirma el horario nuevo y deja claro que el viejo se soltó* (0.7).

## Cómo leerlo

**El criterio 1 engaña si se lee solo.** Si el sistema no hace nada ante la
petición, queda una cita —la vieja— y el criterio da `SÍ` por inacción. El que
delata es el 2: dice si la cita cambió de horario.

El criterio 0 es la causa raíz. Mientras dé `NO`, `agendar_cita` sigue
entregando enlaces, el arnés monta la precondición por webhook y los criterios 2
y 4 no pueden dar otra cosa que `NO`. No son cuatro hallazgos: es uno.
