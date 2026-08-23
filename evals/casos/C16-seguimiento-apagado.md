# C16 — El seguimiento tras el silencio, apagado desde el panel

**Ejecutar:**

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c16_seguimiento_apagado.py -q
```

**Registro:** `evals/.runs/C16-seguimiento-apagado/reporte.md` · **Código:** [`../cases/test_c16_seguimiento_apagado.py`](../cases/test_c16_seguimiento_apagado.py)

## Qué se prueba

Que la clínica pueda **apagar** el seguimiento de interés, y que apagado
signifique *nada* — no "más tarde".

C01 mide que el seguimiento salga; éste mide que no salga cuando no se quiere.
No es la negación trivial de C01: hasta ahora lo único que podía hacer una
clínica que no quisiera perseguir silencios era subir el plazo al máximo, que no
es apagarlo sino esperar más.

## Precondición

Seguimiento de interés a **1 minuto** y encendido. Ninguna cita.

## Pasos

1. Dos mensajes hasta preguntar el precio, igual que C01.
2. Se lee el estado: el aviso tiene que estar ya programado.
3. **Se apaga el interruptor por la ruta del panel** (`POST /admin/api/interest-followup-enabled`).
4. Se lee el estado otra vez.
5. Se adelantan los vencimientos tres veces el plazo.
6. El paciente vuelve a escribir, el bot contesta, y se vuelve a vencer.

## Criterios

| # | Criterio | Esperado |
|---|---|---|
| 1 | Con el interruptor encendido, el seguimiento quedó programado | SÍ |
| 2 | Apagarlo vació lo que ya estaba en cola | SÍ |
| 3 | Pasado el plazo, no salió ningún mensaje | SÍ |
| 4 | Una nueva respuesta del bot tampoco vuelve a armarlo | SÍ |
| 5 | Tampoco sale nada en el segundo vencimiento | SÍ |

Sin métrica de juez: no hay nada que juzgar sobre el texto, porque el resultado
correcto es que no haya texto.

## Cómo leerlo

**El orden importa.** El interruptor se apaga *después* de armar el aviso, y ése
es el caso que de verdad puede fallar. No encolar cuando ya está apagado es
fácil; lo difícil es que lo ya encolado no salga — ni al vencer, ni al volver a
encender el interruptor semanas después.

**Por qué el criterio 1 es un criterio y no un `assert`.** Si no hubiera aviso
programado, los cuatro siguientes saldrían verdes sin demostrar nada: estarían
midiendo que no pasa nada donde nunca iba a pasar nada.

**Por qué se usa la ruta del panel** y no `runtime_settings` a mano, al revés que
los sliders: aquí el interruptor hace dos cosas, guardar el ajuste y vaciar la
cola. Un caso que escribiera sólo el ajuste probaría media conducta y daría por
bueno un apagado que deja avisos vivos esperando.

El criterio 4 cierra la puerta de atrás: si apagado siguiera encolando, bastaría
con encender el interruptor un momento para que saliera todo de golpe.

**Lo que este caso no cubre**, y está en `tests/test_followup_switches.py`: que
el botón *Enviar seguimiento ahora* del panel responda `disabled` en vez de
mandar, y que los dos interruptores sean independientes.
