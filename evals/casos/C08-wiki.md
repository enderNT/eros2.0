# C08 — F-WIKI: preguntar con palabras de paciente, no de índice

**Ejecutar:**

```bash
.venv-evals/bin/python -m pytest evals/cases/test_c08_wiki.py -q
```

**Registro:** `evals/.runs/C08-wiki/reporte.md` · **Código:** [`../cases/test_c08_wiki.py`](../cases/test_c08_wiki.py)

## Qué se prueba

El riesgo de recuperación ya documentado en `E2E-CHECKLIST.md`:
`Knowledge.find_sections` empareja los términos de la consulta contra los
**títulos** de sección, no contra el cuerpo. El agente sabe que debe consultar
por título — se lo dice la descripción de la herramienta — pero el paciente no
escribe títulos.

## Pasos

Tres preguntas por datos que **sí** están en la wiki, sin usar nunca las
palabras del título:

| Pregunta | Sección real |
|---|---|
| `cuánto me sale lo del papel para mi perrito del avión?` | Certificado ESA |
| `a qué hora abren?` | Horarios de atención |
| `puedo pagar con tarjeta?` | Precios y formas de pago |

## Criterios

| # | Criterio | Esperado |
|---|---|---|
| 1–3 | Contesta con el dato correcto en cada una | SÍ |
| 11–13 | No dice "no encontré información" teniendo el dato | SÍ |

El informe anota, por pregunta, **qué herramientas se llamaron**. Ahí se ve si el
modelo tradujo la pregunta a un título de índice o disparó a ciegas.

## Cómo leerlo

Un `NO` en los criterios 11–13 es el fallo **F-WIKI**. No es del modelo ni de la
wiki: es del índice. Lo que hay que anotar es la **pregunta exacta** que falló —
esa lista es la que decide si conviene mejorar los títulos de las secciones o
cambiar la búsqueda para que mire también el cuerpo.
