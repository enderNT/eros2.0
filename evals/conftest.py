"""Configuración común de los casos.

Tres cosas y ninguna más: que `evals` sea importable desde cualquier caso, que
deepeval no hable con nadie que no sea el sistema bajo prueba, y la opción
`--calendario` que decide cuánto sistema real entra. El juez se configura en
`harness/judge.py`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from evals.harness.calendario import VARIABLE, modo_configurado

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Sin esto deepeval manda telemetría a cada ejecución y avisa de actualizaciones
# a mitad de la salida. Una prueba no debería hablar con nadie que no sea el
# sistema bajo prueba.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("DEEPEVAL_UPDATE_WARNING_OPT_IN", "NO")
os.environ.setdefault("ERROR_REPORTING", "NO")


# `load_settings()` lee `.env` con ruta relativa: los casos se ejecutan desde la
# raíz del repo pase lo que pase, para que no dependa de dónde se lanzó pytest.
os.chdir(REPO_ROOT)


def _clave_del_env_file() -> None:
    """El juez lee `os.environ`; la app lee `.env`. Aquí se juntan los dos.

    No sobreescribe nada que ya venga del entorno: si el operador exportó otra
    clave a propósito, esa gana.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    archivo = REPO_ROOT / ".env"
    if not archivo.is_file():
        return
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        nombre, _, valor = linea.partition("=")
        if nombre.strip() == "ANTHROPIC_API_KEY" and valor.strip():
            os.environ["ANTHROPIC_API_KEY"] = valor.strip().strip("\"'")
            return


_clave_del_env_file()


@pytest.fixture(scope="session", autouse=True)
def _exige_clave() -> None:
    """Fallar pronto y claro: sin clave no hay ni sistema bajo prueba ni juez."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.fail("falta ANTHROPIC_API_KEY (ni en el entorno ni en .env)")


def pytest_addoption(parser: pytest.Parser) -> None:
    """`--calendario` decide cuánto sistema real entra en la prueba.

    Es una opción y no una variable suelta porque tiene que quedar dicha en la
    orden que se ejecutó: quien lea después un informe necesita saber en qué modo
    salió, y el modo también acaba escrito en el propio informe.
    """
    parser.addoption(
        "--calendario",
        action="store",
        default=None,
        choices=("fake", "real"),
        help=(
            "fake (por defecto): calendario determinista en memoria."
            " real: disponibilidad y enlaces desde Calendly, sólo lectura."
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    elegido = config.getoption("--calendario")
    if elegido:
        os.environ[VARIABLE] = elegido


def pytest_report_header(config: pytest.Config) -> str:
    return f"calendario: {modo_configurado()}  ·  kapso: doble en memoria (siempre)"
