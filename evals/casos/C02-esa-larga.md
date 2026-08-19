# C02 — Certificado ESA con desvíos: ¿reencarrila y aguanta 17 turnos?

**Ejecutar:**

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c02_esa_larga.py -q -s
```

**Registro:** `evals/.runs/C02-esa-larga/reporte.md` · **Código:** [`../cases/test_c02_esa_larga.py`](../cases/test_c02_esa_larga.py)

> Marcado `lento`: 17 turnos son 34 llamadas al modelo más las del juez. Queda
> fuera de `-m "not lento"`.

## Qué se prueba

Dos cosas que en la vida real llegan juntas: que el asistente devuelva la
conversación a su cauce cuando el paciente se va por las ramas, y que no se
degrade en una conversación larga.

El tema es el **certificado de animal de apoyo emocional (ESA)**, que sí está en
la wiki — $2,000 MXN, cartilla de vacunación vigente, requisitos según aerolínea
— así que hay un dato duro que perseguir del principio al final.

## Pasos

Diecisiete mensajes del paciente en cuatro tramos, escritos en el fichero de
prueba y no improvisados:

| Turnos | Tramo | Qué contienen |
|---|---|---|
| 1–4 | en tema | qué incluye el certificado, cuánto cuesta, cuánto tarda |
| 5–8 | desvío suave | anécdotas del perro, razas, gatos, restaurantes, chalecos |
| 9–12 | desvío duro | aerolíneas baratas, el clima, si es un bot, sueldos |
| 13–17 | vuelta | requisitos y **repregunta del costo ya dicho en el tramo 1** |

## Criterios

| # | Criterio | Esperado |
|---|---|---|
| 1 | Dio el costo de $2,000 MXN en los primeros turnos | SÍ |
| 2 | Repitió el mismo costo al final, tras la compactación | SÍ |
| 3 | Mencionó la cartilla de vacunación al preguntar por requisitos | SÍ |
| 4 | La conversación llegó a compactarse | SÍ |

Métricas del juez: *Reconduce sin cortar en seco*, *No se contradice*,
*No inventa datos de la clínica*.

## Cómo leerlo

El criterio 2 es el que importa. Con `WINDOW_TOKEN_BUDGET = 2000` la
compactación se dispara a mitad de esta conversación y los turnos viejos se
resumen; si el precio se pierde o cambia después del turno ~10, el resumen no
conservó lo importante y el fallo es de compactación, no del modelo.

El criterio 4 existe para que el 2 signifique algo: si la conversación **no**
llegó a compactarse, el criterio 2 pasó por la razón equivocada y el caso no
probó lo que dice probar. El informe anota el watermark del resumen.
