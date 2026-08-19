"""C11 — Handoff desde el panel.

Documentado en `evals/casos/C11-handoff.md`.

El interruptor manual es la garantía de que una persona puede tomar la
conversación. Se acciona por las mismas rutas que usa el SPA del panel, con su
cookie de sesión, no llamando al repositorio por dentro.
"""

from __future__ import annotations

from evals.harness import Report, cerrar, world

CASO = "C11"


async def test_silenciar_y_reactivar_desde_el_panel() -> None:
    reporte = Report(CASO, "Handoff desde el panel")
    async with world("C11-handoff", debounce_seconds=1.0) as w:
        # Tema que la clínica sí ofrece: si se pregunta por algo que no está en la
        # wiki, el bot escala y se silencia solo, y entonces el caso mediría ese
        # silencio en vez del interruptor del panel.
        await w.say("hola, quiero información de terapia individual para ansiedad")
        await w.say("llevo meses con ataques de ansiedad y quiero empezar")

        antes = w.state()
        reporte.criterio(
            0,
            "El bot no se había silenciado solo antes de tocar el panel",
            not antes.muted,
            esperado=True,
            nota="Si esto sale NO, el resto del caso no mide el panel sino una escalada.",
        )

        await w.panel_mute(True)
        callado = await w.say("sigues ahí?")
        entrantes = w.db.execute(
            "SELECT COUNT(*) AS n FROM message WHERE direction = 'inbound'"
        ).fetchone()["n"]

        reporte.criterio(
            1,
            "Con el bot silenciado no hubo respuesta",
            len(callado.replies) == 0,
            esperado=True,
        )
        reporte.criterio(
            2,
            "El mensaje del paciente quedó registrado igualmente",
            entrantes == 3,
            esperado=True,
            nota=f"mensajes entrantes: {entrantes} (la persona que recoge tiene que poder leerlo)",
        )

        await w.panel_mute(False)
        vuelta = await w.say("hola otra vez, seguimos?")
        reporte.criterio(
            3,
            "Tras reactivar vuelve a responder",
            len(vuelta.replies) > 0,
            esperado=True,
        )

        auditoria = w.db.execute(
            "SELECT actor, action FROM audit_log ORDER BY id DESC LIMIT 4"
        ).fetchall()
        acciones = [f"{fila['actor']}:{fila['action']}" for fila in auditoria]
        reporte.criterio(
            4,
            "Los dos cambios aparecen en el registro de auditoría",
            len(acciones) >= 2,
            esperado=True,
            nota=f"últimas entradas: {', '.join(acciones)}",
        )
        cerrar(reporte, w)
