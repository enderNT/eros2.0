# C04 — El paciente se cae después del recordatorio

**Ejecutar:**

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c04_caida_tras_recordatorio.py -q
```

Una rama suelta:

```bash
.venv-evals/bin/python -m pytest "evals/cases/test_c04_caida_tras_recordatorio.py::test_se_cae_tras_el_recordatorio[A-confirma-True]" -q
```

**Registro:** `evals/.runs/C04-A-confirma/reporte.md` y `evals/.runs/C04-B-silencio/reporte.md` · **Código:** [`../cases/test_c04_caida_tras_recordatorio.py`](../cases/test_c04_caida_tras_recordatorio.py)

## Qué se prueba

El caso más caro de la vida real: el recordatorio ya salió y el paciente avisa a
última hora de que no llega. Dos ramas, porque hoy no existe ningún estado de
"confirmado por el paciente" y conviene saber si esa ausencia se nota.

- **Rama A** — confirma asistencia ("sí, ahí estaré") y luego se cae.
- **Rama B** — no contesta al recordatorio y luego se cae.

## Precondición

| Ajuste | Valor |
|---|---|
| Recordatorio de cita | 30 min |

Cita confirmada a 35 minutos vista, con el flujo completo de conversación. El
recordatorio se dispara con `fire_due(at=cita − 29 min)`: no se esperan 24 horas
ni se falsea el reloj del proceso, se le pasa el instante a `send_due(now)`, que
para eso lo acepta.

## Criterios (idénticos en las dos ramas)

| # | Criterio | Esperado |
|---|---|---|
| 1 | El recordatorio salió al vencer su hora | SÍ |
| 2 | La cita sigue vigente pese al aviso por chat | SÍ |
| 3 | El hueco sigue bloqueado en el calendario | SÍ |
| 4 | No se disparó un segundo recordatorio | SÍ |
| 5 | Hubo un solo recordatorio en total | SÍ |

> **En `--calendario real`, los criterios sobre la ocupación del hueco quedan informativos.** La reserva se simula por webhook, así que el hueco nunca llega a ocuparse en Calendly: responder que sí o que no sería inventarse el dato.

Métrica del juez: *Deja claro qué hay que hacer para liberar la cita* (0.7).

## Cómo leerlo

Los criterios 2 y 3 esperan `SÍ` y son **huecos**, no aciertos: el hueco muerto
se queda bloqueado hasta que alguien lo cancele a mano. Lo que el caso mide de
verdad es cuánto de eso le queda claro al paciente, y de eso responde la métrica.

Los criterios 4 y 5 son de idempotencia: el outbox se consume al enviar, así que
un segundo recordatorio significaría que la fila no se consumió — **bug**, y de
los que el paciente nota.

**Compara las dos ramas.** Hoy "sí, ahí estaré" no se guarda en ninguna parte.
Si los dos informes salen idénticos, esa es la respuesta: confirmar no cambia
nada, y merece anotarse como hueco propio.
