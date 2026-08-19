"""`agente-pruebas`: la superficie de mando del arnés.

Por qué existe. Ejecutar un caso a mano exige saber cuatro cosas a la vez: qué
intérprete, dónde viven los ficheros, cómo se llama la opción del calendario y
dónde queda el informe. Eso es contexto que hay que cargar antes de empezar —
caro si quien ejecuta es una persona con prisa, y literalmente caro en tokens si
quien ejecuta es un agente. El CLI convierte todo eso en verbos:

    listar     qué casos hay y qué mide cada uno
    correr     ejecutar uno, varios o todos
    resumen    el estado de la última ejecución de cada caso, en una tabla
    informe    el registro completo de un caso
    doctor     comprobar el entorno antes de gastar un peso en modelo

Es deliberadamente específico de este proyecto: conoce sus casos, su arnés y su
carpeta de informes. Lo reutilizable no es este fichero, es la forma — un mando
único, verbos en vez de rutas, y ninguna decisión que haya que recordar.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CASOS = RAIZ / "evals" / "casos"
PRUEBAS = RAIZ / "evals" / "cases"
RUNS = RAIZ / "evals" / ".runs"

VERDE, ROJO, AMARILLO, GRIS, FIN = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"
COLOR_ESTADO = {"OK": VERDE, "FALLA": ROJO, "PARCIAL": AMARILLO, "BLOQUEADO": GRIS}


def _celda(texto: str, ancho: int, color: str = "") -> str:
    """Rellena según el texto visible: el color no ocupa columnas pero sí caracteres."""
    relleno = " " * max(ancho - len(texto), 0)
    return f"{color}{texto}{FIN if color else ''}{relleno}"


# --------------------------------------------------------------- utilidades


def _casos() -> dict[str, dict[str, str]]:
    """Los casos, leídos del disco. La lista no se mantiene a mano en dos sitios."""
    encontrados: dict[str, dict[str, str]] = {}
    for doc in sorted(CASOS.glob("C*.md")):
        identificador = doc.name.split("-")[0]
        titulo = ""
        for linea in doc.read_text(encoding="utf-8").splitlines():
            if linea.startswith("# "):
                titulo = linea[2:].split("—", 1)[-1].strip()
                break
        encontrados[identificador] = {"doc": str(doc), "titulo": titulo}
    for prueba in sorted(PRUEBAS.glob("test_c*.py")):
        identificador = "C" + prueba.name.split("_")[1][1:]
        encontrados.setdefault(identificador, {"titulo": "(sin documento)"})["prueba"] = str(prueba)
    return dict(sorted(encontrados.items()))


def _resolver(nombres: list[str]) -> list[str]:
    """`c3`, `C3`, `C03` y `3` son el mismo caso: quien ejecuta no debería adivinar."""
    catalogo = _casos()
    rutas: list[str] = []
    for bruto in nombres:
        clave = "C" + re.sub(r"\D", "", bruto).zfill(2)
        caso = catalogo.get(clave)
        if caso is None or "prueba" not in caso:
            disponibles = ", ".join(k for k, v in catalogo.items() if "prueba" in v)
            raise SystemExit(f"no existe el caso {bruto!r}. Hay: {disponibles}")
        rutas.append(caso["prueba"])
    return rutas


def _informes() -> dict[str, Path]:
    """Un informe por **ejecución**, no por caso.

    C04 corre dos ramas y deja dos directorios; agrupar por caso hacía que una
    tapara a la otra y el resumen enseñaba media verdad.
    """
    return {
        directorio.name: directorio / "reporte.md"
        for directorio in sorted(RUNS.glob("C*"))
        if (directorio / "reporte.md").is_file()
    }


def _caso_de(ejecucion: str) -> str:
    return ejecucion.split("-")[0]


def _hallazgos(texto: str) -> list[str]:
    """Sólo lo de la sección «Hallazgos».

    La cabecera del informe también son viñetas `- **…**`, así que filtrar por la
    forma de la línea colaba fecha, estado y ajustes como si fueran hallazgos.
    """
    _, _, cola = texto.partition("## Hallazgos")
    return [linea[2:].replace("**", "") for linea in cola.splitlines() if linea.startswith("- ")]


CRITERIO = re.compile(
    r"^\| (?P<numero>\d+) \| (?P<texto>.+?) \| (?P<resultado>SÍ|NO|N/A) \|"
    r" (?P<esperado>SÍ|NO|—) \| (?P<lectura>[^|]+?) \| (?P<nota>.*?) \|$",
    re.MULTILINE,
)
METRICA = re.compile(
    r"^### (?P<nombre>.+?) — (?P<veredicto>PASA|FALLA) \((?P<score>[^)]+)\)$",
    re.MULTILINE,
)


def _criterios(texto: str) -> list[dict[str, str]]:
    return [encontrado.groupdict() for encontrado in CRITERIO.finditer(texto)]


def _metricas(texto: str) -> list[dict[str, str]]:
    resultado = []
    for encontrado in METRICA.finditer(texto):
        datos = encontrado.groupdict()
        cola = texto[encontrado.end() :].strip().splitlines()
        datos["razon"] = cola[0].strip() if cola else ""
        resultado.append(datos)
    return resultado


def _campo(texto: str, etiqueta: str) -> str:
    encontrado = re.search(rf"^- \*\*{etiqueta}:\*\* (.+)$", texto, re.MULTILINE)
    return encontrado.group(1).strip() if encontrado else "?"


# ------------------------------------------------------------------ verbos


def cmd_listar(args: argparse.Namespace) -> int:
    informes = _informes()
    print(f"{'caso':<6}{'último estado':<20}título")
    for clave, caso in _casos().items():
        propios = [ruta for nombre, ruta in informes.items() if _caso_de(nombre) == clave]
        estado, color = "(sin ejecutar)", GRIS
        if propios:
            estados = [_campo(ruta.read_text(encoding="utf-8"), "Estado") for ruta in propios]
            # Con varias ramas manda la peor: una rama roja no se compensa con otra verde.
            orden = ["FALLA", "BLOQUEADO", "PARCIAL", "OK"]
            estado = min(estados, key=lambda e: orden.index(e) if e in orden else 99)
            if len(propios) > 1:
                estado = f"{estado} ({len(propios)} ramas)"
            color = COLOR_ESTADO.get(estado.split(" ")[0], "")
        marca = "" if "prueba" in caso else f" {GRIS}(sólo documento){FIN}"
        print(f"{clave:<6}{_celda(estado, 20, color)}{caso['titulo']}{marca}")
    print(f"\n{GRIS}documento de cada caso: evals/casos/  ·  informes: evals/.runs/{FIN}")
    return 0


def cmd_correr(args: argparse.Namespace) -> int:
    objetivos = _resolver(args.casos) if args.casos else [str(PRUEBAS)]
    orden = [sys.executable, "-m", "pytest", *objetivos, "-q", "--calendario", args.calendario]
    if args.rapido:
        orden += ["-m", "not lento"]
    if args.parar:
        orden += ["-x"]
    if args.verboso:
        orden += ["-s"]
    print(f"{GRIS}$ {' '.join(orden)}{FIN}\n")
    if args.calendario == "real":
        print(
            f"{AMARILLO}calendario real: se consulta la agenda de la clínica"
            f" (sólo lectura; no se reserva ni se cancela nada allí).{FIN}\n"
        )
    codigo = subprocess.run(orden, cwd=RAIZ).returncode
    print()
    cmd_resumen(argparse.Namespace(caso=None))
    return codigo


def cmd_resumen(args: argparse.Namespace) -> int:
    informes = _informes()
    if not informes:
        print("no hay informes todavía: ejecuta `correr` primero")
        return 1
    print(f"{'ejecución':<20}{'estado':<12}{'ajustes':<46}fecha")
    for clave, ruta in informes.items():
        texto = ruta.read_text(encoding="utf-8")
        if args.caso and _caso_de(clave) != "C" + re.sub(r"\D", "", args.caso).zfill(2):
            continue
        estado = _campo(texto, "Estado")
        ajustes = _campo(texto, "Ajustes usados")
        print(
            f"{clave:<20}{_celda(estado, 12, COLOR_ESTADO.get(estado, ''))}"
            f"{ajustes:<46}{_campo(texto, 'Fecha')}"
        )

    hallazgos = [
        (clave, linea)
        for clave, ruta in informes.items()
        for linea in _hallazgos(ruta.read_text(encoding="utf-8"))
    ]
    if hallazgos:
        print("\nhallazgos acumulados")
        for clave, linea in hallazgos:
            print(f"  {clave}  {linea}")
    return 0


HALLAZGOS_MD = RAIZ / "HALLAZGOS.md"

CABECERA = """<!-- GENERADO por `python -m evals hallazgos`. No editar a mano:
     se reescribe entero en cada ejecución. Las decisiones humanas
     (gravedad, si un hueco debería existir, qué se arregla) van en
     E2E-CASOS.md, que sí se mantiene a mano. -->

# Hallazgos

Lo que las pruebas conversacionales han encontrado, destilado de los informes de
`evals/.runs/` — que no entran al repo porque se regeneran en cada ejecución y
llevan transcripciones completas. Este fichero sí entra: es la memoria.

Tres cosas, y no se mezclan:

* **Huecos** — el sistema no hace algo porque *nunca se implementó*. No es un bug.
* **Desviaciones** — la realidad se apartó de lo documentado. O se rompió algo, o
  alguien tapó un hueco y el caso está desactualizado. Piden que alguien mire.
* **Métricas reprobadas** — el juez encontró un problema de comportamiento del
  modelo, no de código.
"""


def cmd_hallazgos(args: argparse.Namespace) -> int:
    """Destila los informes en un documento único y versionable."""
    informes = _informes()
    if not informes:
        raise SystemExit("no hay informes: ejecuta `correr` primero")

    huecos: list[tuple[str, dict[str, str]]] = []
    desviaciones: list[tuple[str, dict[str, str]]] = []
    reprobadas: list[tuple[str, dict[str, str]]] = []
    ejecutados: list[tuple[str, str, str, str, bool]] = []

    for clave, ruta in informes.items():
        texto = ruta.read_text(encoding="utf-8")
        for criterio in _criterios(texto):
            lectura = criterio["lectura"].strip()
            if lectura == "hueco confirmado":
                huecos.append((clave, criterio))
            elif lectura == "DESVIACIÓN":
                desviaciones.append((clave, criterio))
        for metrica in _metricas(texto):
            if metrica["veredicto"] == "FALLA":
                reprobadas.append((clave, metrica))
        ejecutados.append(
            (
                clave,
                _campo(texto, "Estado"),
                _campo(texto, "Fecha"),
                _campo(texto, "Ajustes usados"),
                _obsoleto(_caso_de(clave), ruta),
            )
        )

    lineas = [CABECERA, ""]
    lineas += _tabla_huecos(huecos)
    lineas += _tabla_desviaciones(desviaciones)
    lineas += _tabla_metricas(reprobadas)
    lineas += _tabla_cobertura(ejecutados)

    contenido = "\n".join(lineas).rstrip() + "\n"
    if args.mostrar:
        print(contenido)
        return 0
    HALLAZGOS_MD.write_text(contenido, encoding="utf-8")
    print(f"escrito {HALLAZGOS_MD.relative_to(RAIZ)}")
    print(
        f"  {len(huecos)} hueco(s), {len(desviaciones)} desviación(es),"
        f" {len(reprobadas)} métrica(s) reprobada(s)"
    )
    return 0


def _obsoleto(clave: str, informe: Path) -> bool:
    """¿El informe es anterior al caso o al arnés que lo produjo?

    Un informe viejo miente con total aplomo: dice OK de un código que ya cambió.
    Comparar fechas de modificación no es exacto, pero avisa de lo único que
    importa aquí — que ese resultado hay que volver a sacarlo antes de creérselo.
    """
    caso = _casos().get(clave, {}).get("prueba")
    referencias = [Path(caso)] if caso else []
    referencias += list((RAIZ / "evals" / "harness").glob("*.py"))
    referencias += list((RAIZ / "src" / "agente").rglob("*.py"))
    ultimo = max((ref.stat().st_mtime for ref in referencias if ref.is_file()), default=0)
    return informe.stat().st_mtime < ultimo


def _tabla_huecos(filas: list[tuple[str, dict[str, str]]]) -> list[str]:
    if not filas:
        return ["## Huecos", "", "Ninguno detectado en los informes disponibles.", ""]
    lineas = [
        "## Huecos",
        "",
        "Funcionalidad que no existe. Confirmado por una prueba, no supuesto.",
        "",
        "| ID | Ejecución | Qué no ocurre | Por qué |",
        "|---|---|---|---|",
    ]
    for clave, criterio in filas:
        lineas.append(
            f"| {_caso_de(clave)}-{criterio['numero']} | {clave} | {criterio['texto']} |"
            f" {criterio['nota'] or '—'} |"
        )
    return lineas + [""]


def _tabla_desviaciones(filas: list[tuple[str, dict[str, str]]]) -> list[str]:
    if not filas:
        return [
            "## Desviaciones (candidatos a bug)",
            "",
            "Ninguna: todo lo ejecutado se comportó como está documentado.",
            "",
        ]
    lineas = [
        "## Desviaciones (candidatos a bug)",
        "",
        "La realidad se apartó de lo documentado. Cada una necesita triaje humano:"
        " o es un bug, o el caso quedó desactualizado.",
        "",
        "| ID | Ejecución | Criterio | Dio | Se esperaba | Nota |",
        "|---|---|---|---|---|---|",
    ]
    for clave, criterio in filas:
        lineas.append(
            f"| {_caso_de(clave)}-{criterio['numero']} | {clave} | {criterio['texto']} |"
            f" {criterio['resultado']} | {criterio['esperado']} | {criterio['nota'] or '—'} |"
        )
    return lineas + [""]


def _tabla_metricas(filas: list[tuple[str, dict[str, str]]]) -> list[str]:
    if not filas:
        return ["## Métricas reprobadas", "", "Ninguna.", ""]
    lineas = ["## Métricas reprobadas", ""]
    for clave, metrica in filas:
        lineas += [
            f"### {clave} — {metrica['nombre']} ({metrica['score']})",
            "",
            metrica["razon"],
            "",
        ]
    return lineas


def _tabla_cobertura(filas: list[tuple[str, str, str, str, bool]]) -> list[str]:
    catalogo = _casos()
    ejecutados = {_caso_de(fila[0]) for fila in filas}
    sin_ejecutar = [clave for clave in catalogo if clave not in ejecutados]
    lineas = [
        "## Cobertura",
        "",
        "De qué se puede hablar y de qué no. Un caso sin ejecutar no es un caso en verde.",
        "",
        "| Ejecución | Estado | Ajustes | Fecha |",
        "|---|---|---|---|",
    ]
    for clave, estado, fecha, ajustes, obsoleto in filas:
        marca = " ⚠️ informe anterior al último cambio de código" if obsoleto else ""
        lineas.append(f"| {clave} | {estado}{marca} | {ajustes} | {fecha} |")
    for clave in sin_ejecutar:
        lineas.append(f"| {clave} | **sin ejecutar** | — | — |")
    return lineas + [""]


def cmd_informe(args: argparse.Namespace) -> int:
    clave = "C" + re.sub(r"\D", "", args.caso).zfill(2)
    propios = {n: r for n, r in _informes().items() if _caso_de(n) == clave}
    if not propios:
        raise SystemExit(f"{clave} no tiene informe todavía: `correr {clave}` primero")
    for nombre, ruta in propios.items():
        if len(propios) > 1:
            print(f"{GRIS}=== {nombre} ==={FIN}\n")
        print(ruta.read_text(encoding="utf-8"))
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    """Todo lo que puede impedir una ejecución, comprobado antes de gastar."""
    fallos = 0

    def revisar(etiqueta: str, ok: bool, ayuda: str) -> None:
        nonlocal fallos
        print(f"  [{VERDE + 'ok' + FIN if ok else ROJO + 'no' + FIN}] {etiqueta}")
        if not ok:
            fallos += 1
            print(f"       {GRIS}{ayuda}{FIN}")

    print("entorno")
    try:
        import deepeval  # noqa: F401

        revisar("deepeval instalado", True, "")
    except ImportError:
        revisar("deepeval instalado", False, 'pip install -e ".[evals]" en .venv-evals')
    try:
        import agente  # noqa: F401

        revisar("paquete agente importable", True, "")
    except ImportError:
        revisar("paquete agente importable", False, 'pip install -e ".[evals]"')

    print("configuración")
    clave = bool(os.environ.get("ANTHROPIC_API_KEY")) or "ANTHROPIC_API_KEY" in (
        (RAIZ / ".env").read_text(encoding="utf-8") if (RAIZ / ".env").is_file() else ""
    )
    revisar("ANTHROPIC_API_KEY disponible", clave, "expórtala o ponla en .env")
    try:
        from agente.config import load_settings

        ajustes = load_settings()
        revisar("configuración de la app válida", True, "")
        revisar(
            "credenciales de Calendly (sólo para --calendario real)",
            bool(ajustes.calendly_token and ajustes.calendly_event_type_uri),
            "CALENDLY_TOKEN y CALENDLY_EVENT_TYPE_URI en .env",
        )
        revisar(
            "contenido de la clínica legible",
            (ajustes.content_dir / "wiki.md").is_file(),
            f"falta {ajustes.content_dir}/wiki.md",
        )
    except Exception as exc:  # noqa: BLE001 - el doctor reporta, no propaga
        revisar("configuración de la app válida", False, str(exc))

    veredicto = "todo listo" if not fallos else f"{fallos} problema(s) antes de poder correr"
    print(f"\n{veredicto}")
    return 1 if fallos else 0


# ------------------------------------------------------------------- mando


def main(argv: list[str] | None = None) -> int:
    padre = argparse.ArgumentParser(
        prog="pruebas",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    verbos = padre.add_subparsers(dest="verbo", required=True)

    verbos.add_parser("listar", help="casos disponibles y su último estado").set_defaults(
        func=cmd_listar
    )

    correr = verbos.add_parser("correr", help="ejecutar casos")
    correr.add_argument("casos", nargs="*", help="C3, c03, 3… vacío = todos")
    correr.add_argument(
        "--calendario",
        choices=("fake", "real"),
        default=os.environ.get("EVAL_CALENDARIO", "fake"),
        help="fake: doble determinista (por defecto). real: Calendly, sólo lectura",
    )
    correr.add_argument("--rapido", action="store_true", help="saltar los casos marcados lentos")
    correr.add_argument("--parar", action="store_true", help="parar en el primer fallo")
    correr.add_argument("--verboso", action="store_true", help="no capturar la salida")
    correr.set_defaults(func=cmd_correr)

    resumen = verbos.add_parser("resumen", help="estado de la última ejecución de cada caso")
    resumen.add_argument("caso", nargs="?")
    resumen.set_defaults(func=cmd_resumen)

    informe = verbos.add_parser("informe", help="registro completo de un caso")
    informe.add_argument("caso")
    informe.set_defaults(func=cmd_informe)

    hallazgos = verbos.add_parser("hallazgos", help="destilar los informes en HALLAZGOS.md")
    hallazgos.add_argument(
        "--mostrar", action="store_true", help="imprimir en vez de escribir el fichero"
    )
    hallazgos.set_defaults(func=cmd_hallazgos)

    verbos.add_parser("doctor", help="comprobar el entorno antes de gastar").set_defaults(
        func=cmd_doctor
    )

    args = padre.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
