# C01 — Interés que se enfría: ¿alguien vuelve a escribirle?

**Ejecutar:**

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c01_seguimiento.py -q
```

**Registro:** `evals/.runs/C01-seguimiento/reporte.md` · **Código:** [`../cases/test_c01_seguimiento.py`](../cases/test_c01_seguimiento.py)

## Qué se prueba

Que a quien preguntó y se calló **antes de llegar a agendar** se le escriba una
vez para retomar el contacto.

Este caso llevaba desde el principio documentando un hueco (HUECO-01): el único
seguimiento que existía colgaba de un enlace de reserva, y quien sólo preguntó
el precio nunca recibió ninguno. Ahora existe un segundo seguimiento, el de
**interés**, y el caso pasa a exigirlo.

## Los dos avisos automáticos, y por qué no son el mismo

| | Recordatorio de cita | Seguimiento tras el silencio |
|---|---|---|
| A quién | Ya tiene un horario confirmado | Nunca llegó a tener uno |
| Qué dice | "Tienes una cita el jueves a las 4" | "¿Sigues por ahí?" |
| Rango | 1 min – 7 días | 1–90 min |
| Ajuste | `appointment_reminder_minutes` | `interest_followup_minutes` |
| Panel | *Recordatorio de cita* | *Seguimiento de interés* |
| Arnés | `set_reminder_minutes` | `set_interest_followup_minutes` |
| Se puede apagar | Sí — ver [C17](C17-recordatorio-apagado.md) | Sí — ver [C16](C16-seguimiento-apagado.md) |

Comparten el outbox y nada más. Uno es un servicio a quien ya pidió su cita; el
otro, una aproximación a quien nunca llegó a pedirla.

**Hubo un tercero.** El bot mandaba un enlace de Calendly y un seguimiento
preguntaba "¿pudiste agendar tu cita?" a quien no volvía. Desde que `agendar_cita`
reserva por API no hay enlace, y ese seguimiento se quedó sin forma de dispararse:
se eliminó entero en la migración 0009 en vez de dejarlo de adorno en el panel.

## Precondición

Seguimiento de interés a **1 minuto**. Ninguna cita.

## Pasos

1. Cuatro mensajes hasta preguntar el precio: `"hola"`, `"vengo buscando terapia
   individual"`, `"es la primera vez que voy a terapia, ando con mucha ansiedad"`,
   `"y cuánto cuesta la primera consulta?"`.
2. Se lee el estado **antes** de que venza nada.
3. El paciente se calla; se adelantan los vencimientos tres veces el plazo.
4. Se lee el estado otra vez.

## Criterios

| # | Criterio | Esperado |
|---|---|---|
| 1 | Quedó un seguimiento de interés programado | SÍ |
| 2 | No se programó ningún recordatorio de cita | SÍ |
| 3 | Llegó exactamente un mensaje tras el silencio | SÍ |
| 4 | El seguimiento no inventa una cita que no existe | SÍ |
| 5 | El outbox quedó limpio: el aviso se consume al enviarse | SÍ |
| 6 | Dio el precio real ($1,000 MXN) sin inventar cifras | SÍ |
| 7 | Ofreció agendar en vez de cerrar en seco | SÍ |

Métrica del juez: *No inventa datos de la clínica* (0.8).

## Cómo leerlo

El criterio 1 dice **uno**, no cuatro. Cada respuesta del bot reprograma el mismo
aviso en vez de encolar otro, así que el plazo se cuenta desde lo último que se
dijo — que es cuando de verdad empieza el silencio.

El criterio 2 es el que vigila que no se mezclen los dos mecanismos. Aquí no hay
cita, así que un recordatorio significaría que algo está compartiendo lo que no
debía.

El criterio 4 es la razón de que sean dos mensajes distintos y no uno
parametrizado: a quien no llegó a agendar no se le puede nombrar un horario,
porque no hay ninguno al que referirse.

**Lo que este caso no cubre**, y está en las pruebas unitarias
(`tests/test_interest_followup.py`): que el aviso no salga si la persona ya
agendó entre medias, si la conversación pasó a un humano, o si contestó antes de
que venciera; y el botón *Enviar seguimiento ahora* del panel, que en el arnés es
`w.force_interest_followup()`.
