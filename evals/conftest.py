"""Configuración común de los casos.

Dos cosas y ninguna más: que `evals` sea importable desde cualquier caso, y que
deepeval no intente hablar con su plataforma ni con OpenAI. El juez se configura
en `harness/judge.py`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

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
