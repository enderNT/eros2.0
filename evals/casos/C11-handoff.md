# C11 — Handoff desde el panel

**Ejecutar:**

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c11_handoff.py -q
```

**Registro:** `evals/.runs/C11-handoff/reporte.md` · **Código:** [`../cases/test_c11_handoff.py`](../cases/test_c11_handoff.py)

## Qué se prueba

El interruptor manual, que es la garantía de que una persona puede tomar la
conversación. Se acciona por **las mismas rutas que usa el SPA del panel**, con
su cookie de sesión: `POST /admin/api/login` y `POST /admin/api/mute`. No se
llama al repositorio por dentro, porque entonces no se estaría probando el panel.

## Pasos

1. Dos turnos sobre terapia individual para ansiedad.
2. Silenciar el contacto desde el panel.
3. `msg "sigues ahí?"`
4. Reactivar desde el panel.
5. `msg "hola otra vez, seguimos?"`

## Criterios

| # | Criterio | Esperado |
|---|---|---|
| 0 | El bot no se había silenciado solo antes de tocar el panel | SÍ |
| 1 | Con el bot silenciado no hubo respuesta | SÍ |
| 2 | El mensaje del paciente quedó registrado igualmente | SÍ |
| 3 | Tras reactivar vuelve a responder | SÍ |
| 4 | Los dos cambios aparecen en la auditoría | SÍ |

## Cómo leerlo

El criterio **0** existe por algo que pasó al escribir el caso: la primera
versión hablaba de terapia de pareja, que no está en la wiki, así que el bot
escaló y se silenció **solo** antes de que el panel hiciera nada. El caso pasaba
en verde midiendo el silencio equivocado. Si el criterio 0 sale `NO`, el resto
del informe no habla del panel y hay que cambiar el tema de la conversación.

El criterio 2 es el que hace útil el handoff: la persona que recoge la
conversación tiene que poder leer lo que el paciente escribió mientras el bot
estaba callado. Silenciar no puede significar descartar.
