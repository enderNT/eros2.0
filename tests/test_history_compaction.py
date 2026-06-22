"""Reglas de compaction del historial conversacional."""

import agente.app as app_mod


class FakeStore:
    def __init__(self, total: int):
        self.turnos = [
            {"id": i + 1, "role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
            for i in range(total)
        ]
        self.saved_summary = None
        self.replaced = None

    def contar_historial(self, conversation_id):
        return len(self.turnos)

    def cargar_historial_completo(self, conversation_id):
        return list(self.turnos)

    def get_resumen(self, conversation_id):
        return "previo"

    def set_resumen(self, conversation_id, summary, user_id=None):
        self.saved_summary = (conversation_id, summary, user_id)

    def reemplazar_historial(self, conversation_id, turnos, user_id=None):
        self.replaced = (conversation_id, turnos, user_id)


def test_compaction_es_exclusiva_del_limite(monkeypatch):
    store = FakeStore(total=4)
    monkeypatch.setattr(app_mod.settings, "history_window", 2)
    monkeypatch.setattr(app_mod.settings, "history_compact_limit", 4)
    monkeypatch.setattr(app_mod.settings, "history_overlap", 1)
    monkeypatch.setattr(app_mod, "compactar_historial", lambda **kwargs: "nuevo")

    app_mod._compactar_historial_si_corresponde(store, {"conversation_id": "c1", "user_id": "u1"})

    assert store.saved_summary is None
    assert store.replaced is None


def test_compaction_resume_viejos_y_conserva_solape_mas_recientes(monkeypatch):
    store = FakeStore(total=6)
    captured = {}
    events = []

    def fake_compactar(**kwargs):
        captured.update(kwargs)
        return "nuevo resumen"

    monkeypatch.setattr(app_mod.settings, "history_window", 2)
    monkeypatch.setattr(app_mod.settings, "history_compact_limit", 4)
    monkeypatch.setattr(app_mod.settings, "history_overlap", 1)
    monkeypatch.setattr(app_mod, "compactar_historial", fake_compactar)
    monkeypatch.setattr(app_mod, "_log_memory_event", lambda **kwargs: events.append(kwargs))

    app_mod._compactar_historial_si_corresponde(
        store,
        {"conversation_id": "c1", "user_id": "u1", "flow_id": "f1", "message_id": "m1"},
    )

    assert captured["resumen_previo"] == "previo"
    assert [t["content"] for t in captured["turnos"]] == ["m0", "m1", "m2", "m3"]
    assert store.saved_summary == ("c1", "nuevo resumen", "u1")
    assert [t["content"] for t in store.replaced[1]] == ["m3", "m4", "m5"]
    assert events[0]["stage"] == "memory_summary_write"
    assert events[0]["request"]["overlap_aplicado"] == 1
