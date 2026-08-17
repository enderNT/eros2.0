"""Load clinic content and deterministically find wiki sections."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
# The playbook section the crisis gate lifts out for a `possible` verdict.
_CRISIS_HEADING = re.compile(r"crisis|riesgo", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Section:
    heading: str
    body: str


class Knowledge:
    def __init__(self, playbook: str, sections: list[Section]) -> None:
        self.playbook, self.sections = playbook, sections
        self.playbook_sections = parse_sections(playbook)

    def crisis_directives(self) -> str:
        """The playbook's crisis section, for the fourth system block (SPEC §7).

        Empty when the playbook has no such section: the gate then adds no
        block rather than inventing guidance for a patient at risk.
        """
        for section in self.playbook_sections:
            if _CRISIS_HEADING.search(section.heading):
                return f"{section.heading}\n{section.body}".strip()
        return ""

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
