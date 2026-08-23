"""C17 — El recordatorio previo a la cita, apagado desde el panel.

Documentado en `evals/casos/C17-recordatorio-apagado.md`.

El gemelo de C16 sobre el otro interruptor, y separado por la misma razón por la
que los interruptores están separados: son dos decisiones distintas. Retomar a
quien se calló es iniciativa de la clínica; recordar una cita que ya existe es
un servicio a quien la pidió. Hay clínicas que querrán lo segundo sin lo primero.

Lo que este caso añade sobre C16 es la vuelta atrás. Apagar los recordatorios
descarta la cola, pero **no** la cita — sigue agendada —, así que volver a
encenderlos tiene que reconstruir el recordatorio de cada cita futura. Si no,
todo el que agendó mientras estuvo apagado se queda sin aviso para siempre y
nadie se entera hasta que alguien no se presenta.
"""

from __future__ import annotations

from evals.harness import Report, cerrar, world

CASO = "C17"
RECORDATORIO_MIN = 30


async def test_recordatorio_apagado_no_avisa() -> None:
    reporte = Report(
        CASO,
        "Recordatorio de cita, apagado",
        ajustes={"recordatorio": f"{RECORDATORIO_MIN} min, luego APAGADO"},
    )
    async with world("C17-recordatorio-apagado", debounce_seconds=1.0) as w:
        w.set_reminder_minutes(RECORDATORIO_MIN)
        reserva = await w.preparar_cita_directa(en_minutos=35)

        armado = w.state()
        reporte.criterio(
            1,
            "Con el interruptor encendido, la cita dejó un recordatorio programado",
            len(armado.reminders) == 1,
            esperado=True,
            nota=(
                "Precondición. Sin recordatorio en cola, apagarlo después no prueba nada."
                f" Cita reservada por el sistema: {reserva.por_el_sistema}."
            ),
        )

        await w.set_reminder_enabled(False)

        tras_apagar = w.state()
        reporte.criterio(
            2,
            "Apagarlo vació la cola de recordatorios",
            not [item for item in tras_apagar.reminders if not item.sent],
            esperado=True,
        )
        reporte.criterio(
            3,
            "La cita sigue agendada: se apagó el aviso, no la reserva",
            len(tras_apagar.scheduled) == 1,
            esperado=True,
            nota=(
                "El interruptor es del recordatorio. Si se llevara la cita por delante"
                " sería un cancelador disfrazado, y nadie espera eso de un checkbox."
            ),
        )

        salidas = await w.fire_due(at=reserva.slot_utc)
        reporte.criterio(
            4,
            "Llegada la hora del aviso, no salió ningún recordatorio",
            len(salidas) == 0,
            esperado=True,
            nota=f"salieron {len(salidas)} mensaje(s) con el recordatorio apagado",
        )

        # La vuelta atrás: encenderlo reconstruye el aviso de las citas que siguen en pie.
        await w.set_reminder_enabled(True)
        reencendido = w.state()
        reporte.criterio(
            5,
            "Volver a encenderlo reprograma el recordatorio de la cita que sigue en pie",
            len([item for item in reencendido.reminders if not item.sent]) == 1,
            esperado=True,
            nota=(
                "Sin esto, quien agendó mientras estuvo apagado no recibiría nunca su"
                " recordatorio, y el fallo sería mudo hasta que alguien no se presente."
            ),
        )

        cerrar(reporte, w)
