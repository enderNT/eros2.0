# C18 — Dos silencios en la misma conversación: ¿dos seguimientos?

**Ejecutar:**

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c18_silencios_repetidos.py -q
```

**Registro:** `evals/.runs/C18-{corta,media,larga}/reporte.md` · **Código:** [`../cases/test_c18_silencios_repetidos.py`](../cases/test_c18_silencios_repetidos.py)

## Qué se prueba

C01 mide **un** silencio. Éste mide qué pasa cuando la misma persona se calla,
vuelve, y se calla otra vez — que es lo que de verdad hace la gente.

La respuesta esperada es que **sí**, que reciba otro aviso. No hay ningún tope de
seguimientos por conversación, y este caso existe en buena parte para dejar esa
ausencia por escrito: si algún día se pone un límite, el criterio 3 se pone rojo
y alguien tiene que decidir a propósito cuál es el número, en vez de descubrirlo
cuando un paciente se queje de que lo persiguen.

## Las tres ramas

| Rama | Turnos del paciente | Para qué |
|---|---|---|
| `corta` | 5 | Por debajo de la compactación |
| `media` | 17 | La misma longitud que ya usa C02 |
| `larga` | 24 | Bien pasada la compactación |

Lo que varía es la longitud de la conversación antes del primer silencio, y la
frontera que interesa no son los turnos sino la **compactación**: al resumirse,
el historial deja de ser la lista de mensajes y pasa a ser un resumen. Merece la
pena comprobar que el seguimiento se arma y se cancela igual a los dos lados de
esa línea, porque cuelga de `on_outbound` y `on_inbound`, que no saben nada de
resúmenes — y ésa es exactamente la clase de suposición que se rompe callando.

Las veinticuatro preguntas son distintas entre sí a propósito. Repetir la misma
para hacer bulto mediría la paciencia del modelo, no la mecánica del seguimiento.

## Precondición

Seguimiento tras el silencio a **1 minuto** y encendido. Ninguna cita.

## Pasos

1. `turnos` mensajes del paciente, sin repetir ninguno.
2. Se lee el estado: tiene que haber **un** aviso programado, no `turnos`.
3. Se adelantan los vencimientos tres veces el plazo → primer seguimiento.
4. El paciente contesta y manda un mensaje más.
5. Se lee el estado: tiene que haberse armado un aviso **nuevo**.
6. Se adelantan los vencimientos otra vez → segundo seguimiento.

## Criterios

| # | Criterio | Esperado |
|---|---|---|
| 0 | La conversación llegó a compactarse | *informativo* |
| 1 | Tras el último mensaje quedó un seguimiento programado | SÍ |
| 2 | Llegó exactamente un seguimiento tras el primer silencio | SÍ |
| 3 | Al volver a hablar, se armó un seguimiento nuevo | SÍ |
| 4 | Llegó un segundo seguimiento tras el segundo silencio | SÍ |
| 5 | El outbox quedó limpio: los dos avisos se consumieron | SÍ |
| 6 | En total salieron dos seguimientos, ni uno más | SÍ |
| 7 | Ningún seguimiento inventa una cita que no existe | SÍ |
| 8 | No se programó ningún recordatorio de cita | SÍ |
| 9 | Dio el precio real ($1,000 MXN) sin inventar cifras | SÍ |

Métrica del juez: *No inventa datos de la clínica* (0.8).

## Cómo leerlo

**El criterio 3 es la pregunta del caso.** Es donde se ve que un segundo silencio
merece un segundo aviso, y el único sitio donde se notaría que alguien puso un
tope.

**El criterio 6 es su contrapeso.** Dos silencios, dos avisos: un tercero sería
el bot persiguiendo solo. Sin este criterio, un bug que rearmara el seguimiento
al enviarlo pasaría por "funciona" — y sería un bucle.

**El criterio 0 no aprueba ni reprueba.** La compactación depende del presupuesto
de tokens, no del número de turnos; exigir un lado concreto convertiría este caso
en un test del compactador. Lo que hace es dejar registrado a qué lado se midió,
para que quien lea el informe sepa si esta ejecución probó lo que la rama
pretendía probar.

**El criterio 9 persigue un dato duro a través del resumen.** El precio se
pregunta al principio, y en las ramas largas la respuesta ya está compactada
cuando termina la conversación.

**Lo que este caso no cubre.** El seguimiento apagado, que es [C16](C16-seguimiento-apagado.md).
Y cuántos silencios seguidos aguanta antes de resultar molesto: eso no es una
pregunta técnica, es una decisión de la clínica que hoy nadie ha tomado.
