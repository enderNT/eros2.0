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
