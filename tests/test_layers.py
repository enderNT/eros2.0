"""Layer rule of SPEC §2.1: domain/ depends on nothing else in the project."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def _import_targets(tree: ast.Module, package_parts: list[str]) -> set[str]:
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    targets.add(node.module)
            else:
                kept = len(package_parts) - (node.level - 1)
                if kept < 0:
                    continue
                base = ".".join(package_parts[:kept])
                targets.add(f"{base}.{node.module}" if node.module else base)
    return {target for target in targets if target}


def _is_forbidden(target: str) -> bool:
    if target == "agente":
        return True
    if target == "agente.domain" or target.startswith("agente.domain."):
        return False
    return target.startswith("agente.")


def violations(path: Path, package_parts: list[str]) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        f"{path.name}: imports {target}"
        for target in sorted(_import_targets(tree, package_parts))
        if _is_forbidden(target)
    ]


def test_domain_imports_no_other_layer():
    domain = SRC / "agente" / "domain"
    offenders = []
    for path in sorted(domain.rglob("*.py")):
        # the containing directory chain is the module's package, also for __init__
        package_parts = list(path.parent.relative_to(SRC).parts)
        offenders.extend(violations(path, package_parts))
    assert offenders == []


def test_checker_flags_a_relative_import_into_services(tmp_path):
    module = tmp_path / "sneaky.py"
    module.write_text("from ..services import inbound\n", encoding="utf-8")
    assert violations(module, ["agente", "domain"])


def test_checker_flags_an_absolute_import_into_adapters(tmp_path):
    module = tmp_path / "sneaky.py"
    module.write_text("import agente.adapters.kapso\n", encoding="utf-8")
    assert violations(module, ["agente", "domain"])


def test_checker_allows_stdlib_and_domain_imports(tmp_path):
    module = tmp_path / "clean.py"
    module.write_text(
        "import datetime\nfrom zoneinfo import ZoneInfo\nfrom agente.domain import errors\n",
        encoding="utf-8",
    )
    assert violations(module, ["agente", "domain"]) == []
