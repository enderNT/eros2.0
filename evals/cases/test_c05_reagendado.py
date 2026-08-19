"""C05 — Reagendado: la cita nueva que puede quedarse sin dueño.

Documentado en `evals/casos/C05-reagendado.md`.

Cuando alguien reagenda desde el correo de Calendly, Calendly emite un
`invitee.canceled` y un `invitee.created` nuevo. `BookingService._created` exige
que el evento traiga el `utm_content` del token para saber de quién es.

Aquí se separan dos preguntas que es fácil confundir:

* **Qué hace nuestro código** si el evento nuevo llega sin tracking. Eso se
  prueba aquí, es determinista y no necesita Calendly.
* **Qué manda Calendly de verdad** en un reagendado. Eso no lo puede saber un
  test: hace falta reservar y pulsar *Reschedule* una vez, a mano. El
  procedimiento está en el markdown del caso.
"""

from __future__ import annotations

from datetime import timedelta

from evals.harness import Report, cerrar, world

CASO = "C05"


async def test_reagendado_sin_tracking_pierde_la_cita() -> None:
    reporte = Report(CASO, "Reagendado sin tracking propagado")
    async with world("C05-reagendado", debounce_seconds=1.0) as w:
        w.set_reminder_minutes(60)
        uri, slot = await w.preparar_cita(en_minutos=300)
        assert len(w.state().scheduled) == 1

        # Reagendado tal como lo emitiría Calendly si NO propagara el tracking:
        # se cancela el evento viejo y se crea otro con un `utm_content` vacío.
        await w.cancel(uri)
        nuevo_slot = slot + timedelta(hours=2)
        await w._post_calendly(
            {
                "event": "invitee.created",
                "payload": {
                    "event": "https://api.calendly.com/scheduled_events/reagendado-sin-tracking",
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
            all(c.status == "canceled" for c in estado.appointments),
            esperado=True,
        )
        reporte.criterio(
            2,
            "Se registró la cita nueva del reagendado",
            len(estado.scheduled) == 1,
            esperado=False,
            nota=(
                "Sin `utm_content` el servicio la descarta como `calendly_booking_unlinked`:"
                " no adivina de quién es una reserva, y hacerlo confirmaría una cita a la"
                " persona equivocada."
            ),
        )
        reporte.criterio(
            3,
            "Quedó un recordatorio para el horario nuevo",
            any(not r.sent for r in estado.reminders),
            esperado=False,
            nota="Consecuencia del criterio 2: sin cita registrada no hay a qué recordar.",
        )
        reporte.criterio(
            4,
            "El paciente recibió algún aviso de que su reagendado no quedó registrado",
            any("no qued" in salida.text.lower() for salida in w.channel.sent[-2:]),
            esperado=False,
            nota="El descarte es silencioso: sólo deja una línea de log.",
        )
        cerrar(reporte, w)
