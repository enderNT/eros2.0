# C17 — El recordatorio previo a la cita, apagado desde el panel

**Ejecutar:**

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c17_recordatorio_apagado.py -q
```

**Registro:** `evals/.runs/C17-recordatorio-apagado/reporte.md` · **Código:** [`../cases/test_c17_recordatorio_apagado.py`](../cases/test_c17_recordatorio_apagado.py)

## Qué se prueba

Que el recordatorio previo a la cita también se pueda apagar, **por su cuenta**,
y que volver a encenderlo recupere lo que se había descartado.

## Por qué son dos interruptores y no uno

| | Seguimiento de interés | Recordatorio de cita |
|---|---|---|
| Qué es | Iniciativa de la clínica: retomar a quien se calló | Servicio a quien ya pidió la cita |
| Se arma | Cuando el bot responde a alguien sin cita | Cuando se confirma una cita |
| Apagarlo | Descarta la cola; no hay nada que recuperar | Descarta la cola; la **cita** sigue en pie |
| Encenderlo | No resucita nada | Reconstruye el aviso de cada cita futura |
| Ruta | `POST /admin/api/interest-followup-enabled` | `POST /admin/api/appointment-reminder-enabled` |
| Arnés | `set_interest_followup_enabled` | `set_reminder_enabled` |

Hay clínicas que querrán lo segundo sin lo primero, y ésa es toda la razón de que
no sea un único interruptor de "avisos automáticos".

## Precondición

Recordatorio a **30 minutos** y encendido. Una cita reservada a 35 minutos vista,
por `preparar_cita_directa`.

## Pasos

1. Se agenda la cita y se lee el estado: tiene que haber un recordatorio en cola.
2. Se apaga el interruptor por la ruta del panel.
3. Se lee el estado otra vez.
4. Se adelantan los vencimientos hasta la hora de la cita.
5. Se **vuelve a encender** el interruptor y se lee el estado una última vez.

## Criterios

| # | Criterio | Esperado |
|---|---|---|
| 1 | Con el interruptor encendido, la cita dejó un recordatorio programado | SÍ |
| 2 | Apagarlo vació la cola de recordatorios | SÍ |
| 3 | La cita sigue agendada: se apagó el aviso, no la reserva | SÍ |
| 4 | Llegada la hora, no salió ningún recordatorio | SÍ |
| 5 | Volver a encenderlo reprograma el recordatorio de la cita que sigue en pie | SÍ |

## Cómo leerlo

**El criterio 3 es el que evita un desastre silencioso.** El interruptor es del
recordatorio. Si se llevara la cita por delante sería un cancelador disfrazado, y
nadie espera eso de un checkbox.

**El criterio 5 es lo que este caso añade sobre C16.** Apagar descarta la cola
pero no las citas, así que encender tiene que reconstruir un recordatorio por
cada cita futura — incluidas las que se agendaron mientras estuvo apagado. Sin
eso, esas personas se quedan sin aviso para siempre y el fallo es mudo: nadie se
entera hasta que alguien no se presenta.

**Lo que este caso no cubre**, y está en `tests/test_followup_switches.py`: que
el botón *Enviar recordatorio ahora* responda `disabled`, y que apagar los
recordatorios deje intacto el seguimiento de interés.
