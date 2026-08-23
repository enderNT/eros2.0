# C04 — El paciente se cae después del recordatorio

**Ejecutar:**

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c04_caida_tras_recordatorio.py -q
```

**Registro:** `evals/.runs/C04-A-confirma/reporte.md` y `evals/.runs/C04-B-silencio/reporte.md` · **Código:** [`../cases/test_c04_caida_tras_recordatorio.py`](../cases/test_c04_caida_tras_recordatorio.py)

## Qué se prueba

El caso más caro de la vida real: el recordatorio ya salió y el paciente avisa
que no llega. Antes sólo se podía medir cuánto tiempo quedaba un hueco muerto
bloqueado. Ahora el hueco se puede soltar, así que el listón sube — el
asistente tiene que ofrecerlo y, con el sí, hacerlo.

Dos ramas, porque no existe un estado de "confirmado por el paciente" y conviene
seguir midiendo si esa ausencia se nota: soltar el hueco de quien confirmó y de
quien nunca contestó debería dar el mismo resultado.

## Precondición

Recordatorio a **30 minutos**, cita a 35 minutos con `preparar_cita_directa`.

## Pasos

1. Se dispara el recordatorio.
2. Rama **A**: `msg "sí, ahí estaré"`. Rama **B**: silencio.
3. `msg "al final no voy a poder, me surgió algo"` — y se comprueba que **no** cancela todavía.
4. `msg "sí, cancélala por favor"`
5. Se lee el estado y se vuelven a disparar vencimientos.

## Criterios

| # | Criterio | Esperado |
|---|---|---|
| 0 | La cita de la precondición la reservó el propio sistema, sin enlace | SÍ |
| 1 | El recordatorio salió al vencer su hora | SÍ |
| 1b | El recordatorio dice también dónde es, no sólo cuándo | SÍ |
| 2 | Avisar no cancela por sí solo: la cita sigue vigente hasta el sí | SÍ |
| 3 | Con el sí explícito, la cita queda cancelada | SÍ |
| 4 | El hueco se soltó y otro paciente puede tomarlo | SÍ |
| 5 | No se disparó un segundo recordatorio | SÍ |
| 6 | Hubo un solo recordatorio en total en el outbox | SÍ |

Métrica del juez: *Ofrece liberar o mover la cita, en vez de sólo lamentarlo* (0.7).

## Cómo leerlo

El criterio 4 es el dinero del caso: una hora de consulta recuperada en vez de
un hueco muerto que nadie libera.

El criterio 2 es su contrapeso. "No voy a poder" **no** es "cancélala": el
paciente puede querer moverla. Cancelar por iniciativa propia es el daño nuevo
que introduce tener `cancel`, y aquí se vigila.

Comparar las dos ramas sigue siendo el punto: si A y B se comportan distinto,
merece explicación.

## La dirección en el recordatorio

El criterio 1b comprueba que el recordatorio nombre la sede. Se mide aquí y no en
un caso propio porque éste es el único que ya lee un recordatorio de verdad,
salido de la app real.

Va también en la confirmación al agendar, y repetirla no es descuido: entre una
cosa y otra pueden pasar días, y el recordatorio es el mensaje que la persona
tiene abierto justo cuando va saliendo de casa. La dirección sale de
`CALENDLY_LOCATION_VALUE`; sin configurar, los dos mensajes la omiten en vez de
inventarse una.
