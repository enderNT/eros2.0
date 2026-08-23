"""C05 — La cita se mueve desde Calendly: ¿se entera el paciente?

Documentado en `evals/casos/C05-reagendado.md`.

El caso cambió de protagonista. Cuando el enlace lo completaba el paciente, era
él quien podía pulsar *Reschedule* en su correo. Si la reserva la hace el
sistema con un correo de la clínica, el paciente ya no recibe ese correo — y el
único que puede mover una cita desde fuera del chat es **la propia clínica**,
desde la interfaz de Calendly. Que es algo que va a pasar: un imprevisto de la
psicóloga, un hueco que se corre media hora.

Lo que se mide sigue siendo lo mismo y sigue siendo lo importante: Calendly
emite un `invitee.canceled` y un `invitee.created` nuevo, y ese evento nuevo no
trae el `utm_content` de ningún token nuestro. Hoy `BookingService._created` lo
descarta como `calendly_booking_unlinked` y el paciente **no se entera de nada**:
se queda sin recordatorio y creyendo que su cita sigue a la hora vieja.

Antes eso se registraba como hueco aceptado (`esperado=False`). Ahora se exige
arreglado: una cita movida por la clínica que el paciente no conoce es la peor
versión de todas.
"""

from __future__ import annotations

from datetime import timedelta

from evals.harness import Report, cerrar, dice, world

CASO = "C05"


async def test_la_clinica_mueve_la_cita_desde_calendly() -> None:
    reporte = Report(CASO, "Reagendado hecho desde Calendly, fuera del chat")
    async with world("C05-reagendado", debounce_seconds=1.0) as w:
        w.set_reminder_minutes(60)
        reserva = await w.preparar_cita_directa(en_minutos=300)
        reporte.criterio(
            0,
            "La cita de la precondición la reservó el propio sistema, sin enlace",
            reserva.por_el_sistema,
            esperado=True,
        )
        assert len(w.state().scheduled) == 1

        # Un reagendado tal como lo emite Calendly cuando lo hace el anfitrión:
        # se cancela el evento viejo y aparece otro, sin tracking que lo ate a
        # ningún token nuestro — porque no salió de un enlace nuestro.
        await w.cancel(reserva.event_uri)
        nuevo_slot = reserva.slot_utc + timedelta(hours=2)
        await w._post_calendly(
            {
                "event": "invitee.created",
                "payload": {
                    "event": "https://api.calendly.com/scheduled_events/movido-por-la-clinica",
                    "name": "Paciente De Prueba",
                    "email": "paciente@example.test",
                    "tracking": {"utm_content": ""},
                    "questions_and_answers": [
                        {"question": "Número de teléfono", "answer": w.key.contact_phone}
                    ],
                    "scheduled_event": {
                        "start_time": nuevo_slot.isoformat().replace("+00:00", "Z")
                    },
                },
            }
        )

        estado = w.state()
        reporte.criterio(
            1,
            "La cita vieja quedó cancelada",
            all(
                c.status == "canceled"
                for c in estado.appointments
                if c.event_uri == reserva.event_uri
            ),
            esperado=True,
        )
        reporte.criterio(
            2,
            "Se registró la cita nueva del reagendado",
            len(estado.scheduled) == 1,
            esperado=True,
            nota=(
                "Hoy el servicio la descarta como `calendly_booking_unlinked` porque no"
                " trae `utm_content`. Reservando nosotros conocemos el `event_id` y el"
                " correo del invitado, así que hay por dónde atribuirla sin adivinar."
            ),
        )
        reporte.criterio(
            3,
            "Quedó un recordatorio para el horario nuevo",
            any(not r.sent for r in estado.reminders),
            esperado=True,
            nota="Consecuencia del criterio 2: sin cita registrada no hay a qué recordar.",
        )
        reporte.criterio(
            4,
            "El paciente recibió aviso de que su cita cambió de hora",
            any(
                dice(salida.text, "cambi", "movi", "nuevo horario")
                for salida in w.channel.sent[-3:]
            ),
            esperado=True,
            nota=(
                "Lo más grave del caso. El paciente se presentaría a la hora vieja, o no"
                " se presentaría a la nueva, sin haber hecho nada mal."
            ),
        )
        cerrar(reporte, w)
