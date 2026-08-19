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
| **Calendly** | **doble en memoria** | ofrece una cuadrícula fija de huecos para que el mismo caso dé lo mismo hoy y dentro de un mes |

Los dobles están en [`harness/fakes.py`](harness/fakes.py) e implementan los
mismos puertos (`Channel`, `Calendar`) que usan los servicios, así que todo lo
que hay por debajo corre exactamente igual que desplegado.

**Nada sale de la máquina** salvo las llamadas al modelo. No se envía ningún
WhatsApp. No se toca la agenda real de Calendly. La clave de Kapso y la de
Calendly se sustituyen por valores inertes al arrancar el mundo de pruebas.

---

## 2. Instalación (una vez)

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

## 3. Ejecutar

Desde la raíz del repo, siempre con el intérprete de `.venv-evals`.

```bash
.venv-evals/bin/python -m pytest evals/cases -q
```

Un caso suelto:

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c06_pendientes.py -q
```

Todo menos el caso largo:

```bash
.venv-evals/bin/python -m pytest evals/cases -q -m "not lento"
```

Con la salida del juez a la vista mientras corre:

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c03_cancelacion.py -q -s
```

**No hace falta levantar `docker compose` ni ngrok.** La app se arranca dentro
del propio proceso de prueba, con su `lifespan` completo.

### Cuánto cuesta y cuánto tarda

Cada turno del paciente son dos llamadas al modelo (clasificador + agente) más,
si hay juez en el caso, una llamada más por métrica al final. Orden de magnitud
por caso: entre 3 y 8 turnos, salvo C02 que son 17 y por eso está marcado
`lento`. La tanda completa ronda los diez minutos.

---

## 4. Qué deja cada ejecución

En `evals/.runs/<caso>/`:

- `reporte.md` — el registro del caso: criterios con su veredicto, métricas del
  juez con su razonamiento, **transcripción literal** de la conversación con lo
  que devolvió cada herramienta, y el estado final de la base.
- `agente.db` — la base de esa ejecución, por si hay que mirarla con `sqlite3`.

El directorio se borra y se rehace en cada ejecución del caso. Si un informe
importa, cópialo fuera antes de volver a ejecutar.

---

## 5. Cómo leer un resultado

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

## 6. Reglas para el agente que ejecuta

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
   se equivoca (ver apartado 7).

---

## 7. Qué hacer cuando el juez se equivoca

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

## 8. Cómo se añade un caso

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

## 9. Índice de casos

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
