# C01 — Interés que se enfría: ¿alguien vuelve a escribirle?

**Ejecutar:**

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c01_seguimiento.py -q
```

**Registro:** `evals/.runs/C01-seguimiento/reporte.md` · **Código:** [`../cases/test_c01_seguimiento.py`](../cases/test_c01_seguimiento.py)

## Qué se prueba

Una conversación de captación normal que llega hasta el precio y se corta. Mide
qué pasa con un posible paciente que se queda a medias: si el sistema lo
recupera o lo pierde en silencio.

## Ajustes

| Ajuste | Valor | Por qué |
|---|---|---|
| Seguimiento de reserva | 1 min | para no esperar 90 minutos a que venza |

Los pone el propio caso llamando al panel; no hay que tocar nada a mano.

## Pasos

1. Cuatro turnos del paciente: saludo, interés por terapia individual, un motivo
   realista, y la pregunta por el precio.
2. El paciente se calla. **No se espera en tiempo real:** el arnés dispara los
   vencimientos con `fire_due(at=ahora + 3 min)`, que es el mismo
   `send_due(now)` que corre en producción, con el instante como argumento.
3. Se lee el estado.

## Criterios

| # | Criterio | Esperado |
|---|---|---|
| 1 | Dio el precio de la valoración ($1,000 MXN) sin inventar cifras | SÍ |
| 2 | Ofreció agendar o dejó la puerta abierta | SÍ |
| 3 | Llegó algún mensaje de seguimiento tras el silencio | **NO** |
| 4 | Quedó algo programado en el outbox | **NO** |

Métrica del juez: *No inventa datos de la clínica* (umbral 0.8).

## Cómo leerlo

Los criterios 3 y 4 dan `NO` **a propósito**, y eso es el hallazgo del caso, no
un fallo. `BookingFollowups.schedule_from_outbound` sólo programa un seguimiento
si el mensaje saliente llevaba un enlace de reserva; sin enlace no hay token, y
sin token no hay nada que programar. Quien sólo preguntó el precio no recibe
nunca nada.

El criterio 4 está para separar dos explicaciones que se confunden fácil: que el
seguimiento estuviera programado y no llegara (sería un bug del outbox) o que
nunca se programara (es el hueco). Si 3 y 4 salen los dos `NO`, es lo segundo.

Registrado como **HUECO-01**. Si algún día se implementa el seguimiento a
interesados sin enlace, este caso pasará a `DESVIACIÓN` y habrá que actualizarlo:
eso es exactamente lo que se busca.
