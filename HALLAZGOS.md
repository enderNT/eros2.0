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
| C05-2 | C05-reagendado | Se registró la cita nueva del reagendado | Sin `utm_content` el servicio la descarta como `calendly_booking_unlinked`: no adivina de quién es una reserva, y hacerlo confirmaría una cita a la persona equivocada. |
| C05-3 | C05-reagendado | Quedó un recordatorio para el horario nuevo | Consecuencia del criterio 2: sin cita registrada no hay a qué recordar. |
| C05-4 | C05-reagendado | El paciente recibió algún aviso de que su reagendado no quedó registrado | El descarte es silencioso: sólo deja una línea de log. |

## Desviaciones (candidatos a bug)

Ninguna: todo lo ejecutado se comportó como está documentado.

## Métricas reprobadas

### C04-A-confirma — Deja claro qué hay que hacer para liberar la cita [Conversational GEval] (0.60 / umbral 0.7)

En el turno donde el paciente avisa de que no podrá asistir, el asistente responde con empatía y ofrece proactivamente reagendar ('¿Quieres que te ayude a reagendarla?'), lo que abre un camino de acción y evita dar el asunto por resuelto sin intervención del paciente. Sin embargo, no indica un mecanismo concreto: no menciona el enlace/correo de Calendly para cancelar o modificar, ni la posibilidad de hablar con alguien del equipo, ni confirma si la cita original quedará cancelada. Queda ambiguo si el hueco de las 2:18 p.m. se libera, por lo que la orientación es parcial aunque no engañosa.

## Cobertura

De qué se puede hablar y de qué no. Un caso sin ejecutar no es un caso en verde.

| Ejecución | Estado | Ajustes | Fecha |
|---|---|---|---|
| C01-seguimiento | OK ⚠️ informe anterior al último cambio de código | seguimiento = 1 min | 2026-08-19T19:38:11+00:00 |
| C04-A-confirma | PARCIAL ⚠️ informe anterior al último cambio de código | recordatorio = 30 min | 2026-08-19T19:43:44+00:00 |
| C04-B-silencio | OK ⚠️ informe anterior al último cambio de código | recordatorio = 30 min | 2026-08-19T19:44:11+00:00 |
| C05-reagendado | OK ⚠️ informe anterior al último cambio de código | (por defecto) | 2026-08-19T19:36:08+00:00 |
| C06-pendientes | OK ⚠️ informe anterior al último cambio de código | (por defecto) | 2026-08-19T19:34:35+00:00 |
| C07-crisis | OK ⚠️ informe anterior al último cambio de código | (por defecto) | 2026-08-19T19:36:44+00:00 |
| C08-wiki | OK ⚠️ informe anterior al último cambio de código | (por defecto) | 2026-08-19T19:32:54+00:00 |
| C10-debounce | OK ⚠️ informe anterior al último cambio de código | calendario = fake, debounce = 4.0 s | 2026-08-19T20:17:32+00:00 |
| C11-handoff | OK ⚠️ informe anterior al último cambio de código | (por defecto) | 2026-08-19T19:31:59+00:00 |
| C12-alcance | OK ⚠️ informe anterior al último cambio de código | (por defecto) | 2026-08-19T19:35:01+00:00 |
| C02 | **sin ejecutar** | — | — |
| C03 | **sin ejecutar** | — | — |
| C09 | **sin ejecutar** | — | — |
