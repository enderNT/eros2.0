#!/usr/bin/env python3
"""Diff-review guard and Markdown-link validator for project-wiki-maintainer."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable

WIKI_ROOT = Path(os.environ.get("PROJECT_WIKI_ROOT", "docs/wiki"))
STATE_FILE = "project-wiki-maintainer.reviewed"
ATTEMPT_FILE = "project-wiki-maintainer.attempts.json"


def run_git(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def git_root() -> Path | None:
    proc = run_git(["rev-parse", "--show-toplevel"], check=False)
    if proc.returncode != 0:
        return None
    return Path(proc.stdout.decode("utf-8", "replace").strip())


def git_dir(root: Path) -> Path:
    proc = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    path = Path(proc.stdout.decode("utf-8", "replace").strip())
    return path if path.is_absolute() else root / path


def status_records(root: Path) -> list[tuple[str, str]]:
    proc = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    chunks = proc.stdout.split(b"\0")
    records: list[tuple[str, str]] = []
    i = 0
    while i < len(chunks):
        raw = chunks[i]
        i += 1
        if not raw:
            continue
        text = raw.decode("utf-8", "surrogateescape")
        if len(text) < 4:
            continue
        code, path = text[:2], text[3:]
        # In -z mode, rename/copy records include a second path field.
        if ("R" in code or "C" in code) and i < len(chunks) and chunks[i]:
            second = chunks[i].decode("utf-8", "surrogateescape")
            i += 1
            records.append((code, second))
        records.append((code, path))
    return records


def normalized(path: str) -> str:
    value = path.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value


def is_ignored_for_review(path: str) -> bool:
    p = normalized(path)
    wiki = normalized(str(WIKI_ROOT)).rstrip("/")
    return (
        p == wiki
        or p.startswith(wiki + "/")
        or p == ".git"
        or p.startswith(".git/")
        or p.startswith(".claude/skills/project-wiki-maintainer/")
        or p in {".claude/settings.json", ".claude/settings.local.json"}
    )


def relevant_records(root: Path) -> list[tuple[str, str]]:
    return [(code, path) for code, path in status_records(root) if not is_ignored_for_review(path)]


def update_file_hash(hasher: "hashlib._Hash", file_path: Path) -> None:
    try:
        if file_path.is_file():
            with file_path.open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    hasher.update(chunk)
        elif file_path.is_symlink():
            hasher.update(os.readlink(file_path).encode("utf-8", "surrogateescape"))
    except OSError as exc:
        hasher.update(f"<unreadable:{exc}>".encode())


def fingerprint(root: Path, records: list[tuple[str, str]] | None = None) -> str | None:
    records = relevant_records(root) if records is None else records
    if not records:
        return None

    hasher = hashlib.sha256()
    for code, path in sorted(records, key=lambda item: (normalized(item[1]), item[0])):
        hasher.update(code.encode("ascii", "replace"))
        hasher.update(b"\0")
        hasher.update(normalized(path).encode("utf-8", "surrogateescape"))
        hasher.update(b"\0")

    tracked_paths = sorted(
        {path for code, path in records if code != "??"},
        key=normalized,
    )
    if tracked_paths:
        diff = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--binary", "HEAD", "--", *tracked_paths],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if diff.returncode != 0:
            # Handles repositories without a first commit.
            for args in (
                ["git", "diff", "--no-ext-diff", "--binary", "--cached", "--", *tracked_paths],
                ["git", "diff", "--no-ext-diff", "--binary", "--", *tracked_paths],
            ):
                proc = subprocess.run(args, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                hasher.update(proc.stdout)
        else:
            hasher.update(diff.stdout)

    for code, path in records:
        if code == "??":
            hasher.update(b"UNTRACKED\0")
            hasher.update(normalized(path).encode("utf-8", "surrogateescape"))
            hasher.update(b"\0")
            update_file_hash(hasher, root / path)

    return hasher.hexdigest()


def state_paths(root: Path) -> tuple[Path, Path]:
    directory = git_dir(root)
    return directory / STATE_FILE, directory / ATTEMPT_FILE


def read_reviewed(root: Path) -> str | None:
    state, _ = state_paths(root)
    try:
        value = state.read_text(encoding="utf-8").strip()
        return value or None
    except OSError:
        return None


def write_reviewed(root: Path, value: str | None) -> None:
    state, attempts = state_paths(root)
    if value:
        state.write_text(value + "\n", encoding="utf-8")
    elif state.exists():
        state.unlink()
    if attempts.exists():
        attempts.unlink()


def next_attempt(root: Path, value: str) -> int:
    _, attempts = state_paths(root)
    data = {"fingerprint": value, "count": 0}
    try:
        previous = json.loads(attempts.read_text(encoding="utf-8"))
        if previous.get("fingerprint") == value:
            data["count"] = int(previous.get("count", 0))
    except (OSError, ValueError, TypeError):
        pass
    data["count"] += 1
    attempts.write_text(json.dumps(data), encoding="utf-8")
    return data["count"]


def relative_paths(records: Iterable[tuple[str, str]]) -> list[str]:
    return sorted({normalized(path) for _, path in records})


def cmd_status(root: Path) -> int:
    records = relevant_records(root)
    value = fingerprint(root, records)
    reviewed = read_reviewed(root)
    payload = {
        "wiki_root": normalized(str(WIKI_ROOT)),
        "changed_files_requiring_review": relative_paths(records),
        "fingerprint": value,
        "reviewed": bool(value and value == reviewed),
        "has_relevant_changes": bool(records),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def cmd_mark_reviewed(root: Path) -> int:
    records = relevant_records(root)
    value = fingerprint(root, records)
    write_reviewed(root, value)
    if value:
        print(f"Recorded wiki review for diff {value[:12]}.")
    else:
        print("No non-wiki changes to record.")
    return 0


def cmd_check_hook(root: Path) -> int:
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        hook_input = {}

    records = relevant_records(root)
    value = fingerprint(root, records)
    if not value or value == read_reviewed(root):
        return 0

    attempt = next_attempt(root, value)
    files = relative_paths(records)
    preview = ", ".join(files[:8])
    if len(files) > 8:
        preview += f", and {len(files) - 8} more"

    # Permit termination after repeated failed continuations instead of creating a loop.
    if attempt > 3 or (hook_input.get("stop_hook_active") and attempt > 2):
        print(
            "Project wiki review is still unrecorded for the current diff. "
            "Run /project-wiki-maintainer update manually before committing.",
            file=sys.stderr,
        )
        return 0

    reason = (
        "The current project diff has not been reviewed for high-level documentation impact. "
        f"Changed files: {preview}. Invoke /project-wiki-maintainer update. "
        "The skill must run mark-reviewed even when it concludes that no wiki content change is needed."
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


def iter_markdown_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.md") if path.is_file())


def clean_link_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    # Markdown titles after a URL are not fully parsed here; common quoted form is supported.
    if ' "' in target:
        target = target.split(' "', 1)[0]
    return target


def cmd_validate_links(root: Path) -> int:
    wiki = root / WIKI_ROOT
    if not wiki.exists():
        print(f"Wiki root does not exist: {WIKI_ROOT}", file=sys.stderr)
        return 1

    problems: list[str] = []
    for page in iter_markdown_files(wiki):
        text = page.read_text(encoding="utf-8", errors="replace")
        for match in LINK_PATTERN.finditer(text):
            target = clean_link_target(match.group(1))
            if not target or target.startswith(("http://", "https://", "mailto:", "#", "data:")):
                continue
            path_part = target.split("#", 1)[0]
            if not path_part:
                continue
            resolved = (page.parent / path_part).resolve()
            try:
                resolved.relative_to(root.resolve())
            except ValueError:
                problems.append(f"{page.relative_to(root)} -> outside project: {target}")
                continue
            if not resolved.exists():
                problems.append(f"{page.relative_to(root)} -> missing: {target}")

    if problems:
        print("Broken relative Markdown links:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1

    count = sum(1 for _ in iter_markdown_files(wiki))
    print(f"Validated relative links in {count} Markdown file(s).")
    return 0


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {
        "status",
        "mark-reviewed",
        "check-hook",
        "validate-links",
    }:
        print(
            "Usage: wiki_guard.py {status|mark-reviewed|check-hook|validate-links}",
            file=sys.stderr,
        )
        return 2

    root = git_root()
    if root is None:
        # Hooks should not block outside Git. Direct skill commands should explain the issue.
        if sys.argv[1] == "check-hook":
            return 0
        print("This command must run inside a Git repository.", file=sys.stderr)
        return 1

    os.chdir(root)
    command = sys.argv[1]
    return {
        "status": cmd_status,
        "mark-reviewed": cmd_mark_reviewed,
        "check-hook": cmd_check_hook,
        "validate-links": cmd_validate_links,
    }[command](root)


if __name__ == "__main__":
    raise SystemExit(main())
