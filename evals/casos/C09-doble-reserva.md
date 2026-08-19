# C09 — "Quiero cambiar mi cita": el hueco de la doble reserva

**Ejecutar:**

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c09_doble_reserva.py -q
```

**Registro:** `evals/.runs/C09-doble-reserva/reporte.md` · **Código:** [`../cases/test_c09_doble_reserva.py`](../cases/test_c09_doble_reserva.py)

## Qué se prueba

El bot no sabe cancelar, pero **sí** sabe agendar. Ante un "quiero moverla", el
camino de menor resistencia es crear una segunda cita y dejar la primera viva.

## Precondición

Una cita confirmada con el flujo completo (`preparar_cita`), recordatorio a 60
minutos.

## Pasos

1. Cita confirmada.
2. `msg "puedo mover mi cita para otro día?"`
3. Si ofrece horarios, se acepta y se completa la reserva del nuevo.
4. Se lee el estado.

## Criterios

| # | Criterio | Esperado |
|---|---|---|
| 1 | Quedaron **dos** citas vigentes a la vez | SÍ |
| 2 | Hay dos recordatorios pendientes para el mismo paciente | SÍ |
| 3 | Los dos huecos quedaron bloqueados en el calendario | SÍ |
| 4 | El panel muestra la cita más temprana | SÍ |

Métrica del juez: *Avisa de que la cita anterior sigue en pie* (0.7).

## Cómo leerlo

Los cuatro `SÍ` describen el hueco, no un acierto. Dos citas vigentes son dos
huecos bloqueados en la agenda y, potencialmente, dos recordatorios al mismo
paciente para dos citas distintas.

El criterio 4 tiene una consecuencia práctica desagradable: `for_contact` ordena
por `slot_utc`, así que el panel enseña la **más temprana** — que suele ser justo
la que el paciente quería abandonar. Quien mire el panel verá la cita equivocada.

Lo único que hoy puede mitigarlo es que el bot avise, y de eso responde la
métrica. Si reprueba, el paciente se queda creyendo que su cita se movió.
