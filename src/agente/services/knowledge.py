"""Load clinic content and deterministically find wiki sections."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Section:
    heading: str
    body: str


class Knowledge:
    def __init__(self, playbook: str, sections: list[Section]) -> None:
        self.playbook, self.sections = playbook, sections

    @classmethod
    def load(cls, playbook_path: Path, wiki_path: Path) -> Knowledge:
        return cls(
            playbook_path.read_text(encoding="utf-8"),
            parse_sections(wiki_path.read_text(encoding="utf-8")),
        )

    def table_of_contents(self) -> str:
        return "\n".join(f"- {section.heading}" for section in self.sections)

    def find_sections(self, query: str) -> str:
        terms = {term for term in re.findall(r"[\wáéíóúüñ]+", query.lower()) if len(term) > 2}
        matches = [section for section in self.sections if terms & _terms(section.heading)]
        if not matches:
            return "No encontré información sobre esa consulta en la wiki."
        selected = matches[:2]
        result = "\n\n".join(f"## {section.heading}\n{section.body}" for section in selected)
        if len(matches) > len(selected):
            result += "\n\nMostré solo las primeras 2 secciones relevantes."
        return result


def parse_sections(text: str) -> list[Section]:
    headings = list(_HEADING.finditer(text))
    return [
        Section(
            match.group(1),
            text[
                match.end() : headings[index + 1].start()
                if index + 1 < len(headings)
                else len(text)
            ].strip(),
        )
        for index, match in enumerate(headings)
    ]


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[\wáéíóúüñ]+", text.lower()))
