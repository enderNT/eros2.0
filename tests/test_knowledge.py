from pathlib import Path

from agente.services.knowledge import Knowledge, Section, parse_sections


def test_toc_and_exact_lookup():
    knowledge = Knowledge(
        "playbook", [Section("Servicios", "contenido"), Section("Precios", "pendiente")]
    )
    assert "Servicios" in knowledge.table_of_contents()
    assert "contenido" in knowledge.find_sections("servicios")


def test_no_match_and_truncation_wording():
    knowledge = Knowledge(
        "", [Section("Citas", "a"), Section("Citas en línea", "b"), Section("Citas urgentes", "c")]
    )
    assert "No encontré" in knowledge.find_sections("desconocido")
    assert "primeras 2" in knowledge.find_sections("citas")


def test_malformed_heading_does_not_crash():
    assert parse_sections("texto sin encabezado\n## Logística\ncontenido") == [
        Section("Logística", "contenido")
    ]


def test_repository_clinic_content_is_loadable_and_searchable():
    content = Path(__file__).parents[1] / "content"
    knowledge = Knowledge.load(content / "playbook.md", content / "wiki.md")

    assert "Nora" in knowledge.playbook
    assert "$1,000 MXN" in knowledge.find_sections("precios")
    assert "Sócrates 128" in knowledge.find_sections("ubicación")
