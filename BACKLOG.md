# BACKLOG.md — cosas pendientes de decidir

Ideas que todavía no son tareas. Cada una describe qué se observa, cómo funciona
hoy y qué habría que decidir; ninguna trae solución cerrada, porque la parte
difícil de todas ellas es acordar el comportamiento, no escribirlo.

Cuando una se decide, se convierte en un caso de `evals/casos/` y desaparece de
aquí.

---

## B1 — El seguimiento no se rearma cuando la conversación se reabre

### Qué se observa

El seguimiento tras el silencio sale unas veces sí y otras no, sin un patrón
evidente desde fuera. Hay un caso donde no salir es lo correcto —el paciente
acaba de confirmar su cita y el bot cierra con "¿hay algo más en que te pueda
ayudar?"; ahí perseguirlo sobra— y otros donde debería salir y no sale: alguien
que pidió reagendar, recibió horarios y se calló.

### Cómo funciona hoy

Dos condiciones que hay que cumplir a la vez, y ninguna vive en el prompt.

**Primera: el mensaje tiene que salir por la ruta normal de respuesta.** El
seguimiento se arma en `on_outbound`, un gancho que sólo dispara `InboundService`
cuando el modelo contesta a un mensaje del paciente. Todo lo demás que el bot
manda sale por otro sitio y no arma nada:

| Mensaje | ¿Arma seguimiento? |
|---|---|
| Respuesta normal del modelo | Sí |
| Aviso de cancelación hecha en Calendly | No |
| Aviso de que la cita se movió desde Calendly | No |
| Recordatorio previo a la cita | No |
| El propio seguimiento | No — y así evita el bucle |
| Mensaje de crisis | No |
| Mensaje de disculpa tras un fallo de envío | No |

**Segunda: el contacto no puede tener una cita vigente.**
`schedule_from_outbound` se corta en seco si `_has_appointment` es verdadero.

Esa segunda condición es la que explica lo que se observa. La pregunta que hace
el código es *"¿tiene cita?"*, y la que habría que hacer es *"¿quedó algo sin
cerrar?"*. Casi siempre coinciden. Cuando no, se nota:

| Situación | Hoy | ¿Debería? |
|---|---|---|
| Confirmó su cita y el bot se despide | No se arma | Correcto |
| Pide cancelar, el bot pide confirmación, se calla | No se arma — la cita sigue vigente | **Probablemente sí** |
| Pide reagendar, el bot ofrece horarios, se calla | No se arma — sigue teniendo la vieja | **Probablemente sí** |
| El bot cancela porque el paciente lo pidió | Se arma | Correcto |
| La clínica cancela desde Calendly | **No se arma** | Por decidir |
| La clínica mueve la cita desde Calendly | No se arma | Correcto: sigue teniendo cita |

Los dos casos de "se calla a mitad" son el mismo fallo visto dos veces: el
paciente está en medio de algo, la cita vieja todavía cuenta como cita, y el
gate lo lee como "ya está atendido".

El de la cancelación desde Calendly es distinto y más incómodo. Al paciente le
llega "tu cita quedó cancelada, si quieres te paso otros horarios" — una
invitación explícita a responder — y es justo el mensaje que no arma nada. Si no
contesta, nadie vuelve a escribirle nunca.

### Por qué no es cosa del prompt

Merece decirlo porque es la intuición natural y lleva a buscar en el sitio
equivocado: el modelo no decide esto ni puede. El seguimiento se programa en
código, fuera de su alcance, a partir de dos hechos —por qué ruta salió el
mensaje y si hay una cita en la base—. Cambiar el prompt no mueve ninguno de los
dos.

### Qué habría que decidir

1. **Cuál es la condición correcta.** "No tiene cita" es fácil de comprobar pero
   responde a otra pregunta. Alternativas: que el último mensaje del bot dejara
   algo abierto, que haya una intención a medias (cancelar, reagendar), o algo
   más simple que todavía no se nos ha ocurrido. Conviene que sea comprobable en
   la base y no una interpretación del texto: el resto de guardas del sistema son
   deterministas por una razón.
2. **Si los avisos que salen fuera de la conversación también deberían armarlo.**
   Sobre todo el de cancelación. Ojo: cualquier cosa que se toque aquí hay que
   comprobarla contra el bucle. Hoy no puede haberlo porque el gancho vive en un
   solo sitio; abrirlo a más mensajes es exactamente cómo aparecería.
3. **Qué pasa con quien se queda a medias y ya tiene cita.** Si se arma el
   seguimiento y luego no contesta, el mensaje actual ("¿sigues por ahí?, te paso
   horarios para la cita de valoración") no encaja: esa persona ya tiene cita, lo
   que dejó a medias fue moverla. Puede que haga falta un texto distinto, y
   entonces la pregunta de si son uno o dos mecanismos se reabre.

### Dónde mirar

- `src/agente/services/interest_followup.py` — el gate `_has_appointment`.
- `src/agente/services/inbound.py` — el único sitio que dispara `on_outbound`.
- `src/agente/app.py` — dónde se encadenan los ganchos.
- `evals/cases/test_c18_silencios_repetidos.py` — el caso que ya fija que dos
  silencios seguidos merecen dos avisos.
