# RUNBOOK.md — pasos de operador

Lo que **no** hace un agente. Cada paso de aquí toca credenciales, servicios en vivo o
pacientes reales. El orden importa: saltarse uno deja el sistema en un estado que parece
funcionar y no funciona.

Estado de partida (2026-08-17): el código está completo (T1–T13). Falta ejecutar esto.

---

## 0. Antes de nada

`CALENDLY_SIGNING_KEY` y `CALENDLY_WEBHOOK_TOKEN` están vacías, y el número de WhatsApp
sigue siendo el temporal de pruebas. Mientras eso siga así, ninguna cita se confirma nunca
—`/webhook/calendly` rechaza todas las entregas— y eso es correcto, no un bug.

---

## 1. Desplegar y obtener la URL pública

Nada de lo demás sirve sin esto: los dos webhooks son entregas *entrantes* desde internet.

- Desplegar en Coolify desde `v3-rebuild`.
- **Declarar un volumen persistente** montado donde apunta `DB_PATH`. Sin él, cada redeploy
  borra el historial, los perfiles y las citas.
- Cargar todas las variables de `.env.example` en el entorno de Coolify.
- Verificar: `curl https://<URL>/health` → `{"status":"ok",...,"database":"ok"}`.

Anotar la URL. En los pasos siguientes es `<URL>`.

---

## 2. Registrar el webhook de Calendly

Necesita `CALENDLY_TOKEN`. Se hace una sola vez.

Primero, obtener los URIs de la cuenta:

```bash
curl -s https://api.calendly.com/users/me -H "Authorization: Bearer $CALENDLY_TOKEN"
```

De la respuesta salen `resource.uri` (el usuario) y `resource.current_organization`.

Generar una llave de firma propia — así se sabe cuál es, en vez de depender de leerla de la
respuesta:

```bash
openssl rand -hex 32
```

Crear la suscripción (sustituir los tres valores):

```bash
curl -s -X POST https://api.calendly.com/webhook_subscriptions -H "Authorization: Bearer $CALENDLY_TOKEN" -H "Content-Type: application/json" -d '{"url":"https://<URL>/webhook/calendly","events":["invitee.created","invitee.canceled"],"organization":"<ORGANIZATION_URI>","user":"<USER_URI>","scope":"user","signing_key":"<LLAVE_GENERADA>"}'
```

Poner esa misma llave en `CALENDLY_SIGNING_KEY` en el entorno de Coolify y reiniciar.

**Verificar que quedó bien:** una entrega sin firma debe dar 401.

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://<URL>/webhook/calendly -d '{}'
```

Si eso devuelve 401, la mitad de seguridad está bien. La otra mitad se verifica reservando
de verdad (bloque D del `E2E-CHECKLIST.md`).

Para listar o borrar suscripciones después:

```bash
curl -s https://api.calendly.com/webhook_subscriptions?scope=user&user=<USER_URI>&organization=<ORGANIZATION_URI> -H "Authorization: Bearer $CALENDLY_TOKEN"
```

---

## 3. Contenido de la clínica

Bloqueado en la clínica, no en nosotros. Ver `content/PREGUNTAS-CLINICA.md`: son ocho
preguntas, y las respuestas se copian tal cual a `content/wiki.md` sustituyendo cada
marcador `<<pendiente>>`.

El **mensaje de crisis** (`CRISIS_MESSAGE`) es aparte y es el string más delicado del
sistema: se envía textual, sin que el modelo lo toque. Tiene que salir aprobado por la
clínica, con los teléfonos verificados uno por uno.

---

## 4. Correr el E2E completo

`E2E-CHECKLIST.md`, con el sink local, **antes** de tocar Kapso. La puerta de salida está
al final de ese archivo. El bloque F (crisis) es el que no admite un solo fallo.

Para el bloque D hace falta un event type real de la clínica, no el `Discovery call` de 15
minutos que se usó para probar la plomería.

---

## 5. Repuntar el webhook de Kapso

**Último paso, y sólo si el paso 4 pasó.** A partir de aquí el bot le contesta a pacientes
reales.

La cuenta de Kapso es **producción en vivo**. Estos comandos los corre una persona, nunca
un agente, nunca desde una tarea automatizada:

```bash
kapso whatsapp webhooks new
```

Apuntarlo a `https://<URL>/webhook/kapso` con el secreto de `KAPSO_WEBHOOK_SECRET`.

Después del primer mensaje real: abrir el panel, confirmar que la conversación aparece, y
tener a mano el **interruptor global** por si hay que parar todo.

---

## Cosas que nunca se automatizan

- `kapso push`, `kapso link`, `kapso login/logout`.
- Cualquier envío real de WhatsApp desde una tarea.
- Registrar o borrar webhooks en Calendly o en Kapso.
- Editar `.env` o rotar credenciales.
