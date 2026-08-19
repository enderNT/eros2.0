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
    return {
        directorio.name.split("-")[0]: directorio / "reporte.md"
        for directorio in sorted(RUNS.glob("C*"))
        if (directorio / "reporte.md").is_file()
    }


def _hallazgos(texto: str) -> list[str]:
    """Sólo lo de la sección «Hallazgos».

    La cabecera del informe también son viñetas `- **…**`, así que filtrar por la
    forma de la línea colaba fecha, estado y ajustes como si fueran hallazgos.
    """
    _, _, cola = texto.partition("## Hallazgos")
    return [linea[2:].replace("**", "") for linea in cola.splitlines() if linea.startswith("- ")]


def _campo(texto: str, etiqueta: str) -> str:
    encontrado = re.search(rf"^- \*\*{etiqueta}:\*\* (.+)$", texto, re.MULTILINE)
    return encontrado.group(1).strip() if encontrado else "?"


# ------------------------------------------------------------------ verbos


def cmd_listar(args: argparse.Namespace) -> int:
    informes = _informes()
    print(f"{'caso':<6}{'último estado':<16}título")
    for clave, caso in _casos().items():
        informe = informes.get(clave)
        estado, color = "(sin ejecutar)", GRIS
        if informe:
            estado = _campo(informe.read_text(encoding="utf-8"), "Estado")
            color = COLOR_ESTADO.get(estado, "")
        marca = "" if "prueba" in caso else f" {GRIS}(sólo documento){FIN}"
        print(f"{clave:<6}{_celda(estado, 16, color)}{caso['titulo']}{marca}")
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
    print(f"{'caso':<6}{'estado':<12}{'ajustes':<46}fecha")
    for clave, ruta in informes.items():
        texto = ruta.read_text(encoding="utf-8")
        if args.caso and clave != "C" + re.sub(r"\D", "", args.caso).zfill(2):
            continue
        estado = _campo(texto, "Estado")
        ajustes = _campo(texto, "Ajustes usados")
        print(
            f"{clave:<6}{_celda(estado, 12, COLOR_ESTADO.get(estado, ''))}"
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


def cmd_informe(args: argparse.Namespace) -> int:
    clave = "C" + re.sub(r"\D", "", args.caso).zfill(2)
    ruta = _informes().get(clave)
    if ruta is None:
        raise SystemExit(f"{clave} no tiene informe todavía: `correr {clave}` primero")
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

    verbos.add_parser("doctor", help="comprobar el entorno antes de gastar").set_defaults(
        func=cmd_doctor
    )

    args = padre.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
