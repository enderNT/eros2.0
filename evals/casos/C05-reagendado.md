# C05 — La cita se mueve desde Calendly: ¿se entera el paciente?

**Ejecutar:**

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c05_reagendado.py -q
```

**Registro:** `evals/.runs/C05-reagendado/reporte.md` · **Código:** [`../cases/test_c05_reagendado.py`](../cases/test_c05_reagendado.py)

## Qué se prueba

El caso cambió de protagonista. Cuando el enlace lo completaba el paciente, era
él quien podía pulsar *Reschedule* en su correo. Si la reserva la hace el
sistema con un correo de la clínica, el paciente ya no recibe ese correo — y el
único que puede mover una cita desde fuera del chat es **la propia clínica**,
desde la interfaz de Calendly.

Eso va a pasar: un imprevisto de la psicóloga, un hueco que se corre media hora.
Y Calendly emite entonces un `invitee.canceled` y un `invitee.created` nuevo que
**no trae el `utm_content` de ningún token nuestro**, porque no salió de un
enlace nuestro.

## Precondición

Cita confirmada con `preparar_cita_directa`, recordatorio a 60 minutos.

## Pasos

1. Cita confirmada.
2. Se simula el reagendado del anfitrión: `invitee.canceled` del evento viejo y
   un `invitee.created` nuevo, dos horas después, sin tracking.
3. Se lee el estado.

## Criterios

| # | Criterio | Esperado |
|---|---|---|
| 0 | La cita de la precondición la reservó el propio sistema, sin enlace | SÍ |
| 1 | La cita vieja quedó cancelada | SÍ |
| 2 | Se registró la cita nueva del reagendado | SÍ |
| 3 | Quedó un recordatorio para el horario nuevo | SÍ |
| 4 | El paciente recibió aviso de que su cita cambió de hora | SÍ |

## Cómo leerlo

Los criterios 2, 3 y 4 **eran hueco aceptado** (`esperado=NO`) y ahora se exigen
arreglados. Es la decisión que este caso documenta: una cita movida por la
clínica que el paciente no conoce es la peor versión de todas — se presenta a la
hora vieja, o no se presenta a la nueva, sin haber hecho nada mal.

Hoy `BookingService._created` descarta el evento como `calendly_booking_unlinked`
porque no trae `utm_content`, y el descarte es **silencioso**: sólo deja una
línea de log. Reservando nosotros conocemos el `event_id` y el correo del
invitado, así que hay por dónde atribuirlo sin adivinar de quién es una reserva.
