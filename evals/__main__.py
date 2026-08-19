"""Permite `python -m evals …` además de `python evals/cli.py …`."""

import sys

from evals.cli import main

if __name__ == "__main__":
    sys.exit(main())
