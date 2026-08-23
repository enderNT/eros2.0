<!-- GENERADO por `python -m evals hallazgos`. No editar a mano:
     se reescribe entero en cada ejecución. Las decisiones humanas
     (gravedad, si un hueco debería existir, qué se arregla) van en
     E2E-CASOS.md, que sí se mantiene a mano. -->

# Hallazgos

Lo que las pruebas conversacionales han encontrado, destilado de los informes de
`evals/.runs/` — que no entran al repo porque se regeneran en cada ejecución y
llevan transcripciones completas. Este fichero sí entra: es la memoria.

Tres cosas, y no se mezclan:

* **Huecos** — el sistema no hace algo porque *nunca se implementó*. No es un bug.
* **Desviaciones** — la realidad se apartó de lo documentado. O se rompió algo, o
  alguien tapó un hueco y el caso está desactualizado. Piden que alguien mire.
* **Métricas reprobadas** — el juez encontró un problema de comportamiento del
  modelo, no de código.


## Huecos

Funcionalidad que no existe. Confirmado por una prueba, no supuesto.

| ID | Ejecución | Qué no ocurre | Por qué |
|---|---|---|---|
| C01-3 | C01-seguimiento | Llegó algún mensaje de seguimiento tras el silencio | HUECO-01: sin enlace de reserva no hay token, y sin token `schedule_from_outbound` no programa nada. |
| C01-4 | C01-seguimiento | Quedó algo programado en el outbox para este contacto | Confirma que el criterio 3 es por ausencia de programación, no por temporizador. |

## Desviaciones (candidatos a bug)

La realidad se apartó de lo documentado. Cada una necesita triaje humano: o es un bug, o el caso quedó desactualizado.

| ID | Ejecución | Criterio | Dio | Se esperaba | Nota |
|---|---|---|---|---|---|
| C02-4 | C02-esa-larga | La conversación llegó a compactarse | NO | SÍ | watermark: sin resumen. Si no compactó, el criterio 2 no probó lo que dice probar. |

## Métricas reprobadas

Ninguna.

## Cobertura

De qué se puede hablar y de qué no. Un caso sin ejecutar no es un caso en verde.

| Ejecución | Estado | Ajustes | Fecha |
|---|---|---|---|
| C01-seguimiento | OK | calendario = fake, seguimiento = 1 min | 2026-08-23T01:49:17+00:00 |
| C02-esa-larga | FALLA | calendario = fake | 2026-08-23T01:51:22+00:00 |
| C03-cancelacion | OK | calendario = fake, recordatorio = 60 min | 2026-08-23T01:51:56+00:00 |
| C04-A-confirma | OK | calendario = fake, recordatorio = 30 min | 2026-08-23T01:52:35+00:00 |
| C04-B-silencio | OK | calendario = fake, recordatorio = 30 min | 2026-08-23T01:53:06+00:00 |
| C05-reagendado | OK | calendario = fake | 2026-08-23T01:53:21+00:00 |
| C06-pendientes | OK | calendario = fake | 2026-08-23T01:53:37+00:00 |
| C07-crisis | OK | calendario = fake | 2026-08-23T01:59:04+00:00 |
| C08-wiki | OK | calendario = fake | 2026-08-23T01:54:29+00:00 |
| C09-doble-reserva | OK | calendario = fake, recordatorio = 60 min | 2026-08-23T01:55:09+00:00 |
| C10-debounce | OK | calendario = fake, debounce = 4.0 s | 2026-08-23T01:55:20+00:00 |
| C11-handoff | OK | calendario = fake | 2026-08-23T01:55:44+00:00 |
| C12-alcance | OK | calendario = fake | 2026-08-23T01:56:06+00:00 |
| C13-cancelacion-ambigua | OK | calendario = fake | 2026-08-23T01:56:45+00:00 |
| C14-arrepentimiento | OK | calendario = fake | 2026-08-23T01:57:31+00:00 |
| C15-cancelar-inexistente | OK | calendario = fake | 2026-08-23T01:57:50+00:00 |
