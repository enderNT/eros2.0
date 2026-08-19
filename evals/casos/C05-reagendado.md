# C05 — Reagendado: la cita nueva que puede quedarse sin dueño

**Ejecutar (parte automática):**

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c05_reagendado.py -q
```

**Registro:** `evals/.runs/C05-reagendado/reporte.md` · **Código:** [`../cases/test_c05_reagendado.py`](../cases/test_c05_reagendado.py)

## Qué se prueba

Cuando alguien reagenda desde el correo de Calendly, Calendly emite un
`invitee.canceled` y un `invitee.created` nuevo. `BookingService._created` exige
que el evento traiga el `utm_content` del token de reserva para saber de quién
es: sin él, la reserva se descarta como `calendly_booking_unlinked`, en silencio.

Aquí hay **dos preguntas distintas** que es fácil confundir, y por eso el caso
tiene dos mitades.

## Parte A — qué hace nuestro código (automática)

Determinista, sin Calendly. El arnés simula el reagendado tal como llegaría si
Calendly **no** propagara el tracking: cancela el evento viejo y crea otro con
`utm_content` vacío.

| # | Criterio | Esperado |
|---|---|---|
| 1 | La cita vieja quedó cancelada | SÍ |
| 2 | Se registró la cita nueva del reagendado | **NO** |
| 3 | Quedó un recordatorio para el horario nuevo | **NO** |
| 4 | El paciente recibió aviso de que su reagendado no quedó registrado | **NO** |

Los tres `NO` son deliberados y describen el comportamiento actual: sin token no
se adivina de quién es una reserva — hacerlo confirmaría una cita a la persona
equivocada — y el descarte sólo deja una línea de log.

## Parte B — qué manda Calendly de verdad (manual, una vez)

Esto ningún test lo puede saber. Hace falta una persona:

1. Levanta el entorno real: `docker compose up -d` y el túnel de ngrok.
2. Conversa hasta que el bot mande el enlace y **reserva de verdad** desde él.
3. `docker compose exec agente python /app/scripts/e2e.py state` — confirma cita
   y recordatorio programado.
4. En el correo de Calendly, pulsa **Reschedule** y elige otro horario.
5. `state` de nuevo.
6. `docker compose logs --tail 100 agente | grep calendly`

**Qué buscar:**

- ¿Aparece `calendly_booking_unlinked` en los logs?
- ¿Hay una cita nueva con el horario nuevo, o sólo la vieja cancelada?
- ¿La cita nueva tiene su propio recordatorio?

## Cómo leerlo

Si en la parte B aparece `calendly_booking_unlinked` y no hay cita nueva, el
riesgo está **confirmado**: reagendar deja al paciente sin cita registrada y sin
recordatorio, sin que nadie se entere. Es **bug grave** y bloquea el uso real.

Si Calendly sí propaga el tracking, la parte A sigue siendo válida como
descripción de qué pasaría si dejara de hacerlo — que es justo la clase de
cambio externo que rompe cosas en silencio.
