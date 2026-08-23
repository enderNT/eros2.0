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

## Los dos seguimientos, y por qué no son el mismo

| | Seguimiento de reserva | Seguimiento de interés |
|---|---|---|
| A quién | Ya tenía un horario concreto | Nunca llegó a tener uno |
| Qué dice | "¿Pudiste agendar tu cita para las 4?" | "¿Sigues por ahí?" |
| Rango | 0–90 min | 1–90 min |
| Ajuste | `booking_followup_minutes` | `interest_followup_minutes` |
| Panel | *Seguimiento de reserva* | *Seguimiento de interés* |
| Arnés | `set_followup_minutes` | `set_interest_followup_minutes` |
| Se puede apagar | No | Sí — ver [C16](C16-seguimiento-apagado.md) |

Hacen lo mismo mecánicamente y responden a cosas distintas. Un solo plazo para
los dos obligaría a la clínica a tratar igual a quien abandonó una reserva y a
quien sólo estaba mirando, y no son lo mismo.

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
| 2 | No se programó ningún seguimiento de reserva | SÍ |
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

El criterio 2 es el que vigila que no se mezclen los dos mecanismos. Aquí nunca
hubo horario ofrecido, así que el de reserva no tiene de qué colgar; si aparece,
algo está compartiendo lo que no debía.

El criterio 4 es la razón de que sean dos mensajes distintos y no uno
parametrizado: a quien no llegó a agendar no se le puede preguntar "¿pudiste
agendar tu cita para las 4?", porque no hay ninguna a la que referirse.

**Lo que este caso no cubre**, y está en las pruebas unitarias
(`tests/test_interest_followup.py`): que el aviso no salga si la persona ya
agendó entre medias, si la conversación pasó a un humano, o si contestó antes de
que venciera; y el botón *Enviar seguimiento ahora* del panel, que en el arnés es
`w.force_interest_followup()`.
