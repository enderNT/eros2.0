# RUNBOOK.md — pasos de operador

Lo que **no** hace un agente. Cada paso toca credenciales, servicios en vivo o pacientes
reales. El orden importa: saltarse uno deja el sistema en un estado que parece funcionar y
no funciona.

---

## 0. Lo que falta hoy

| Qué | Estado | Dónde |
| --- | --- | --- |
| `CALENDLY_INVITEE_EMAIL` | **placeholder** (`citas@example.com`) | `.env` / Coolify |
| `CRISIS_MESSAGE` | puesta, sin revisar por la clínica | `.env` / Coolify |
| Webhook de Kapso | apunta al número temporal de pruebas | Kapso |

`CALENDLY_INVITEE_EMAIL` es bloqueante para reservar: es el correo a nombre del cual queda
cada cita en la agenda. Con el placeholder, todas las citas salen a nombre de un buzón que
no existe.

---

## 1. Calendly: la cuenta y el event type

Esto se comprueba una vez y se olvida, pero si algo de aquí está mal **ninguna reserva
funciona**, y el fallo aparece a mitad de una conversación con un paciente, no al arrancar.

### La cuenta

Reservar en nombre del paciente usa la **Scheduling API** (`POST /invitees`), que exige
**plan de pago**. Un plan gratuito devuelve error en cada reserva.

Basta un **token de acceso personal**. No hace falta registrar una aplicación OAuth.

### El event type

`CALENDLY_EVENT_TYPE_URI` es la URI canónica (`https://api.calendly.com/event_types/<uuid>`),
no el enlace público `calendly.com/…`. Sale de:

```bash
curl -s "https://api.calendly.com/event_types?user=<USER_URI>" -H "Authorization: Bearer $CALENDLY_TOKEN"
```

Cuatro requisitos duros. Se leen de un tirón con:

```bash
curl -s "<CALENDLY_EVENT_TYPE_URI>" -H "Authorization: Bearer $CALENDLY_TOKEN"
```

| Requisito | Qué mirar en la respuesta | Si está mal |
| --- | --- | --- |
| Tiene ubicación declarada | `resource.locations` no vacío | Ninguna reserva se crea |
| El tipo de ubicación es utilizable | `locations[0].kind` **no** es `ask_invitee` | Ninguna reserva se crea |
| La ubicación trae su valor | Con `kind` `physical`, `inbound_call` o `custom`, `locations[0].location` tiene texto | Ninguna reserva se crea |
| Ninguna pregunta obligatoria que no sea un teléfono | En `resource.custom_questions`, toda la que tenga `required: true` es de `type: phone_number` | Ninguna reserva se crea |

**El tipo de ubicación se lee del event type, no de `.env`.** Es la única fuente: la API
compara contra lo que declara el event type, y un ajuste nuestro que discrepara sólo
serviría para mentirnos.

Con `kind: outbound_call` la ubicación es el teléfono **del paciente** —Calendly le llama a
él— y el event type la deja en blanco a propósito. Es el único caso en que un
`location` vacío es correcto.

Las preguntas obligatorias son el requisito que más sorprende. Sólo se puede responder sola
una pregunta de teléfono, porque el teléfono lo sabemos. Cualquier otra pregunta marcada
obligatoria —"¿motivo de la consulta?"— hace fallar **todas** las reservas: inventar la
respuesta pondría una frase falsa en la agenda de la clínica, así que se rechaza en voz
alta. La solución es marcarla opcional en Calendly.

### Qué NO hay que hacer

- **No** crear enlaces de reserva ni repartirlos: el bot reserva por API y el paciente no
  entra a ninguna página.
- **No** poner un event type de prueba (el `Discovery call` de 15 minutos): la duración y la
  ubicación salen de aquí y acaban en la agenda real.
- **No** tocar `CALENDLY_LOCATION_KIND` ni `CALENDLY_SCHEDULING_LINK`: ninguna línea de
  código las lee.
- **No** confundir `CALENDLY_LOCATION_VALUE` con la ubicación de Calendly. Es la dirección
  que se le **dice al paciente** por WhatsApp, en la confirmación y en el recordatorio.
  Mantenerla igual que la de `content/wiki.md`; vacía, los dos mensajes la omiten.
- **No** hace falta el webhook para reservar. Eso es el paso 3, y sirve para otra cosa.

---

## 2. Desplegar y obtener la URL pública

- Desplegar en Coolify desde `v3-rebuild`.
- **Declarar un volumen persistente** montado donde apunta `DB_PATH`. Sin él, cada redeploy
  borra el historial, los perfiles y las citas.
- Cargar todas las variables de `.env.example` en el entorno de Coolify.
- **Si ya hay una base con datos, copiarla antes de desplegar.** Las migraciones corren
  solas al arrancar y algunas reconstruyen tablas enteras; la copia es la única vuelta atrás.
- Verificar: `curl https://<URL>/health` → `{"status":"ok",...,"database":"ok"}`.

Anotar la URL. En los pasos siguientes es `<URL>`.

---

## 3. Registrar el webhook de Calendly

**Para qué sirve:** enterarnos de lo que pasa **fuera** de la conversación — que la clínica
agende, cancele o mueva una cita desde el panel de Calendly. Sobre todo las cancelaciones:
sin webhook, una cita cancelada allí sigue viva para nosotros y el paciente recibe el
recordatorio de una cita que ya no existe.

**Para qué no sirve:** para reservar. Eso ya funciona sin él.

Se puede desplegar y probar sin este paso. Para producción se quiere.

Se hace una sola vez, y necesita `CALENDLY_TOKEN`. **No** se envían los textos con ángulos
(`<URL>`, `<USER_URI>`…): son marcadores para sustituir.

| Campo | Valor y de dónde sale |
| --- | --- |
| `url` | URL **pública HTTPS de esta aplicación**, seguida de `/webhook/calendly`. Sale del campo **Domains** en Coolify. No usar `localhost`, una IP privada ni la URL del panel de Coolify. Comprobar antes con `curl https://<URL>/health`. |
| `events` | Fijos: `invitee.created` e `invitee.canceled`. |
| `organization` | `resource.current_organization` de `GET /users/me`. Forma `https://api.calendly.com/organizations/<uuid>`. |
| `user` | `resource.uri` de `GET /users/me`. Forma `https://api.calendly.com/users/<uuid>`; no es el enlace público. Aunque el error de Calendly hable de `user_uuid`, el campo se llama `user` y lleva esta URI completa. |
| `scope` | Fijo `user`. |
| `signing_key` | Secreto propio: `openssl rand -hex 32`. El mismo valor va en `CALENDLY_SIGNING_KEY` en Coolify. |

Obtener las URIs de la cuenta:

```bash
curl -s https://api.calendly.com/users/me -H "Authorization: Bearer $CALENDLY_TOKEN"
```

Crear la suscripción:

```bash
curl -s -X POST https://api.calendly.com/webhook_subscriptions -H "Authorization: Bearer $CALENDLY_TOKEN" -H "Content-Type: application/json" -d '{"url":"https://<URL>/webhook/calendly","events":["invitee.created","invitee.canceled"],"organization":"<ORGANIZATION_URI>","user":"<USER_URI>","scope":"user","signing_key":"<LLAVE_GENERADA>"}'
```

Poner esa llave en `CALENDLY_SIGNING_KEY` en Coolify y reiniciar.

**Verificar:** una entrega sin firma tiene que dar 401.

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://<URL>/webhook/calendly -d '{}'
```

Ver si ya hay una suscripción registrada, antes de crear otra:

```bash
curl -s "https://api.calendly.com/webhook_subscriptions?scope=user&user=<USER_URI>&organization=<ORGANIZATION_URI>" -H "Authorization: Bearer $CALENDLY_TOKEN"
```

**Alcance de la atribución.** Una cita movida o cancelada en Calendly se reconoce por el
teléfono que nosotros mismos escribimos allí al reservar, y sólo para gente a la que el bot
ya le agendó. Una reserva hecha a mano para alguien que nunca habló con el bot se descarta
en silencio: confirmarle a un paciente la cita de un desconocido es peor que no enterarse.

---

## 4. Contenido de la clínica

`content/wiki.md` ya no tiene marcadores `<<pendiente>>`. Lo que queda es el **mensaje de
crisis** (`CRISIS_MESSAGE`): el string más delicado del sistema, se envía textual sin que el
modelo lo toque. Tiene que salir aprobado por la clínica, con los teléfonos verificados uno
por uno.

La dirección vive en dos sitios y tienen que decir lo mismo: `content/wiki.md`, para cuando
el paciente pregunta, y `CALENDLY_LOCATION_VALUE`, para la confirmación y el recordatorio.

---

## 5. Correr el E2E completo

`E2E-CHECKLIST.md`, con el sink local, **antes** de tocar Kapso. La puerta de salida está al
final de ese archivo. El bloque F (crisis) es el que no admite un solo fallo.

Los casos conversacionales son otra cosa y los puede correr un agente, porque no tocan nada
vivo:

```bash
.venv-evals/bin/python -m evals correr
```

---

## 6. Repuntar el webhook de Kapso

**Último paso, y sólo si el 5 pasó.** A partir de aquí el bot le contesta a pacientes reales.

La cuenta de Kapso es **producción en vivo**. Estos comandos los corre una persona, nunca un
agente, nunca desde una tarea automatizada.

`<PNID>` es `KAPSO_PHONE_NUMBER_ID`. Ver lo que hay registrado:

```bash
kapso whatsapp webhooks list --phone-number-id <PNID> --output json
```

Borrar uno, con el `id` que salga del listado:

```bash
kapso whatsapp webhooks delete <WEBHOOK_ID> --phone-number-id <PNID>
```

Crear el nuevo:

```bash
kapso whatsapp webhooks new --phone-number-id <PNID> --url https://<URL>/webhook/kapso --event whatsapp.message.received --payload-version v2 --active --secret-key <KAPSO_WEBHOOK_SECRET>
```

Sobre el secreto: **manda Kapso, no el `.env`**. Kapso firma con el suyo y la app verifica
con el de `KAPSO_WEBHOOK_SECRET`; si no son idénticos, toda entrega da 400 y no hay ningún
otro síntoma. Pasar `--secret-key` con el valor que ya está en `.env` los deja iguales de
entrada. Si en cambio se deja que Kapso lo genere, sale en el campo `secret_key` del
`list` y hay que copiarlo al `.env`.

Sobre los eventos: uno solo, `whatsapp.message.received`. Es el único que la app entiende;
suscribirse a los demás sólo llena el log de 400.

**Después de tocar `.env`, reiniciar el contenedor.** El fichero se lee al arrancar, así que
editarlo con el servicio ya levantado no cambia nada.

Después del primer mensaje real: abrir el panel, confirmar que la conversación aparece, y
tener a mano el **interruptor global** por si hay que parar todo.

---

## Cosas que nunca se automatizan

- `kapso push`, `kapso link`, `kapso login/logout`.
- Cualquier envío real de WhatsApp desde una tarea.
- Registrar o borrar webhooks en Calendly o en Kapso.
- Editar `.env` o rotar credenciales.
