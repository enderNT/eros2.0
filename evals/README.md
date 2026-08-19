# Cómo se prueban las conversaciones

Este directorio contiene los casos conversacionales, el arnés que los ejecuta y
el registro que dejan al terminar. Está escrito para que lo siga **una persona o
un agente sin criterio propio**: hay una única forma de ejecutar cada caso, y es
la que está aquí.

Si buscas la descripción narrativa de los casos y para qué sirve cada uno, está
en [`../E2E-CASOS.md`](../E2E-CASOS.md). Si buscas cómo ejecutar uno concreto,
está en `casos/CNN-*.md`. Este fichero explica lo que es común a todos.

---

## 1. Qué es real y qué no

La pregunta que hay que poder responder antes de creerse un resultado.

| Pieza | En estas pruebas | Por qué |
|---|---|---|
| Modelo de conversación | **real** (Anthropic, la clave de `.env`) | es el sistema bajo prueba; con un modelo falso no se mide nada |
| Clasificador de crisis | **real** | corre antes que el agente en cada turno |
| Wiki y playbook | **reales** (`content/`) | los datos que puede inventar son justo esos |
| App, rutas, firmas de webhook | **reales** | el mensaje entra por `/webhook/kapso` firmado, igual que en producción |
| Base de datos | **real** (SQLite, con sus migraciones) | una por ejecución, en `evals/.runs/<caso>/` |
| Outbox, recordatorios, seguimiento | **reales** | lo que se mide en la mitad de los casos |
| Panel `/admin` | **real** | los casos que lo tocan usan su API con cookie de sesión |
| **Kapso** | **doble en memoria** | es transporte; mandar WhatsApp de verdad cuesta, ensucia una conversación real y no se puede repetir |
| **Calendly** | **conmutable**: doble en memoria o el real | ver el apartado 2; es el dial del arnés |

Los dobles están en [`harness/fakes.py`](harness/fakes.py) e implementan los
mismos puertos (`Channel`, `Calendar`) que usan los servicios, así que todo lo
que hay por debajo corre exactamente igual que desplegado.

**Nunca se envía un WhatsApp.** Kapso no es conmutable a propósito: mandar
mensajes reales para leer una respuesta no es una prueba, es un envío. Su clave
se sustituye por un valor inerte al arrancar, para que ni un error de cableado
pueda acabar en el teléfono de alguien.

---

## 2. El dial: `--calendario fake` o `--calendario real`

Lo que hace de esto un arnés y no un juego de mocks es que se puede **elegir
cuánto sistema real entra**. Las dos posiciones no compiten: responden preguntas
distintas.

| | `fake` (por defecto) | `real` |
|---|---|---|
| De dónde salen los huecos | cuadrícula fija en memoria | API de Calendly |
| Qué pregunta responde | **comportamiento**: qué dice el bot, qué herramienta usa, qué queda en la base | **integración**: ¿seguimos leyendo bien lo que Calendly devuelve hoy? |
| Repetible | sí | depende de la agenda de esa semana |
| Coste externo | ninguno | lecturas a Calendly |
| Se puede inyectar un hueco a 35 min | sí | no: el caso se adapta al hueco real más cercano |

```bash
.venv-evals/bin/python -m evals correr --calendario real
.venv-evals/bin/python -m pytest evals/cases -q --calendario real   # equivalente
```

**En modo real no se escribe nada en Calendly.** Las herramientas del agente sólo
consultan disponibilidad y copian la `scheduling_url` que ya viene en cada hueco;
`create_invitee` no lo llama nadie. La reserva se sigue simulando con un
`invitee.created` firmado contra nuestro propio webhook.

Eso tiene una consecuencia que conviene tener presente: **en modo real el hueco
nunca llega a ocuparse**. Los criterios que preguntan "¿el hueco siguió
bloqueado?" (C03, C04, C09) no se pueden responder ahí, y en vez de dar un `NO`
falso se registran como **informativos**. El modo usado queda escrito en cada
informe, porque dos informes del mismo caso en modos distintos no son
comparables.

Confirmar qué manda Calendly en un **reagendado** sigue necesitando a una persona
pulsando *Reschedule*: eso está en la parte B de
[`casos/C05-reagendado.md`](casos/C05-reagendado.md).

---

## 3. Instalación (una vez)

deepeval arrastra un árbol de dependencias que no pinta nada en la imagen que se
despliega, así que vive en su propio entorno:

```bash
python3 -m venv .venv-evals && .venv-evals/bin/pip install -e ".[evals]"
```

Comprobación de que quedó bien:

```bash
.venv-evals/bin/python -m pytest evals/cases --collect-only -q
```

Debe listar 13 pruebas (12 casos; C04 corre dos ramas).

### Claves

Sólo hace falta `ANTHROPIC_API_KEY`. Se toma del entorno y, si no está, de
`.env`. Se usa para dos cosas distintas que conviene no confundir:

- el **sistema bajo prueba**, con el modelo que diga la configuración de la app;
- el **juez** de deepeval, con `EVAL_JUDGE_MODEL` (por defecto `claude-opus-5`).

Que el juez sea un modelo distinto del que conversa no es un detalle: un sistema
que se califica a sí mismo tiende a aprobarse.

---

## 4. Ejecutar

Hay un mando para esto. Evita tener que recordar rutas, el nombre de la opción
del calendario y dónde queda el informe:

```bash
.venv-evals/bin/python -m evals doctor          # ¿está todo antes de gastar?
.venv-evals/bin/python -m evals listar          # qué casos hay y cómo salieron
.venv-evals/bin/python -m evals correr C10      # C10, c10, 10 — da igual
.venv-evals/bin/python -m evals correr C3 C9 --calendario real
.venv-evals/bin/python -m evals correr --rapido # todo menos los lentos
.venv-evals/bin/python -m evals resumen         # tabla + hallazgos acumulados
.venv-evals/bin/python -m evals informe C06     # el registro completo
```

`correr` termina imprimiendo el resumen, así que una sola orden deja a la vista
qué pasó y qué se encontró.

Por debajo es pytest, y se puede usar directamente cuando haga falta algo que el
mando no expone:

```bash
.venv-evals/bin/python -m pytest evals/cases -q
.venv-evals/bin/python -m pytest evals/cases/test_c03_cancelacion.py -q -s
.venv-evals/bin/python -m pytest evals/cases -q -m "not lento" --calendario real
```

**No hace falta levantar `docker compose` ni ngrok.** La app se arranca dentro
del propio proceso de prueba, con su `lifespan` completo.

### Cuánto cuesta y cuánto tarda

Cada turno del paciente son dos llamadas al modelo (clasificador + agente) más,
si hay juez en el caso, una llamada más por métrica al final. Orden de magnitud
por caso: entre 3 y 8 turnos, salvo C02 que son 17 y por eso está marcado
`lento`. La tanda completa ronda los diez minutos.

---

## 5. Qué deja cada ejecución

En `evals/.runs/<caso>/`:

- `reporte.md` — el registro del caso: criterios con su veredicto, métricas del
  juez con su razonamiento, **transcripción literal** de la conversación con lo
  que devolvió cada herramienta, y el estado final de la base.
- `agente.db` — la base de esa ejecución, por si hay que mirarla con `sqlite3`.

El directorio se borra y se rehace en cada ejecución del caso. Si un informe
importa, cópialo fuera antes de volver a ejecutar.

---

## 6. Cómo leer un resultado

Cada criterio declara qué debería pasar **según el código de hoy**, no según lo
que sería deseable. De ahí salen tres lecturas y no se deben mezclar:

| Lectura | Qué significa | ¿Falla la prueba? |
|---|---|---|
| `ok` | funciona como está documentado | no |
| `hueco confirmado` | el sistema no hace algo porque **nunca se implementó** | no |
| `DESVIACIÓN` | la realidad se apartó de lo documentado | **sí** |

Un hueco confirmado no rompe la prueba a propósito: si cada noche saliera rojo
por algo que nadie va a arreglar hoy, el rojo dejaría de significar nada. Lo que
rompe la prueba es la desviación, y hay exactamente dos explicaciones: se rompió
algo, o alguien tapó el hueco y el caso está desactualizado. Las dos piden que
una persona mire.

Las métricas del juez sí hacen fallar el caso cuando no llegan a su umbral.

---

## 7. Reglas para el agente que ejecuta

Las mismas ocho del protocolo de `E2E-CASOS.md`, con lo que cambia al ejecutarse
desde aquí:

1. **No inventes pasos.** Los pasos son el fichero de prueba. Si un caso no se
   puede ejecutar, se reporta bloqueado con el error; no se busca otra ruta.
2. **No edites un caso para que pase.** Si un criterio falla, el resultado es el
   fallo. Cambiar el criterio para ver verde es falsificar el informe.
3. **No toques la base a mano.** Todo pasa por el arnés o por el panel.
4. **El estado manda sobre el chat.** El apartado "Estado final" del informe gana
   sobre lo que el bot haya prometido en la conversación.
5. **Que el bot diga "no sé" no es un fallo.** La wiki tiene huecos declarados
   (`<<pendiente>>`). Lo sancionable es inventar.
6. **Un criterio, una respuesta binaria.** Ya lo son: los escribe el arnés.
7. **Reporta el informe, no tu resumen de él.** El fichero `reporte.md` es la
   evidencia; el resumen se escribe encima, no en lugar de él.
8. **Si el juez reprueba, lee su razón antes de creerle.** Un juez sin evidencia
   se equivoca (ver apartado 8).

---

## 8. Qué hacer cuando el juez se equivoca

Pasa, y la forma más común está resuelta: al principio el juez marcaba como
inventado el precio de $1,000 MXN, que sale literal de la wiki. No mentía —
sólo veía el texto final, donde un dato correcto y uno inventado se parecen
exactamente igual.

La solución está en el arnés: envuelve las herramientas y guarda lo que devolvió
cada una, y ese texto viaja al juez como `retrieval_context` del turno. La
rúbrica le dice explícitamente que un dato presente ahí es correcto *aunque le
parezca improbable*.

Si aun así una métrica reprueba algo que a ojo está bien:

1. Lee la razón del juez en `reporte.md`. Suele nombrar la frase exacta.
2. Mira si esa frase está en la evidencia de ese turno, en la transcripción.
3. Si está y el juez no la vio, el problema es la rúbrica → ajusta los
   `evaluation_steps` en [`harness/judge.py`](harness/judge.py), no el caso.
4. Si no está, el juez tiene razón y hay un hallazgo que registrar.

---

## 9. Cómo se añade un caso

1. Escribe primero el markdown en `casos/CNN-nombre.md`, con la misma estructura
   que los que ya hay: qué se prueba, qué está bajo prueba, pasos, criterios con
   su valor esperado, y cómo leer el resultado.
2. Escribe `cases/test_cNN_nombre.py` usando el arnés. Las piezas son:

   ```python
   async with world("CNN-nombre", debounce_seconds=1.0) as w:
       await w.say("...")  # un turno del paciente
       await w.burst(["...", "..."])  # varios dentro de la ventana
       uri, slot = await w.preparar_cita(en_minutos=35)  # cita confirmada
       await w.fire_due(at=slot - timedelta(minutes=29))  # vencer lo pendiente
       await w.cancel(uri)  # invitee.canceled de Calendly
       await w.panel_mute(True)  # el panel, por su propia API
       estado = w.state()  # citas, outbox, mute, perfil
   ```
3. Todo criterio lleva `esperado=`. Sin eso el informe no puede distinguir un
   hueco de un bug, que es la distinción de la que depende todo lo demás.
4. Termina con `cerrar(reporte, w)`.

Referencia completa del arnés: [`harness/world.py`](harness/world.py).

---

## 10. Índice de casos

Orden sugerido: de barato y sin dependencias a caro y con estado real.

| Caso | Qué mide | Doc | Coste |
|---|---|---|---|
| C10 | Ráfaga y debounce | [casos/C10-debounce.md](casos/C10-debounce.md) | 1 turno |
| C08 | F-WIKI: recuperación con palabras de paciente | [casos/C08-wiki.md](casos/C08-wiki.md) | 3 turnos |
| C06 | No inventa lo que la wiki declara pendiente | [casos/C06-pendientes.md](casos/C06-pendientes.md) | 3 turnos + juez |
| C12 | Fuera de alcance clínico | [casos/C12-alcance.md](casos/C12-alcance.md) | 3 turnos + juez |
| C01 | Interés que se enfría: ¿hay seguimiento? | [casos/C01-seguimiento.md](casos/C01-seguimiento.md) | 4 turnos + juez |
| C11 | Handoff desde el panel | [casos/C11-handoff.md](casos/C11-handoff.md) | 4 turnos |
| C07 | Crisis a mitad de conversación | [casos/C07-crisis.md](casos/C07-crisis.md) | 5 turnos |
| C05 | Reagendado sin tracking (+ parte manual) | [casos/C05-reagendado.md](casos/C05-reagendado.md) | 3 turnos |
| C03 | Cancelación con horas de antelación | [casos/C03-cancelacion.md](casos/C03-cancelacion.md) | ~5 turnos + juez |
| C09 | Doble reserva al pedir cambio | [casos/C09-doble-reserva.md](casos/C09-doble-reserva.md) | ~7 turnos + juez |
| C04 | Caída tras el recordatorio (2 ramas) | [casos/C04-caida-tras-recordatorio.md](casos/C04-caida-tras-recordatorio.md) | ~6 turnos ×2 + juez |
| C02 | ESA con desvíos, 17 turnos | [casos/C02-esa-larga.md](casos/C02-esa-larga.md) | **17 turnos + 3 jueces** |
