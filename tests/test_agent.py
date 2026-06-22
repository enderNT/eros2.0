"""Tests del loop ReAct (agent.responder) con un cliente Anthropic falso."""

import agente.agent as A


# --- Bloques y respuestas falsas emulando la forma del SDK -------------------

class TextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class ToolUseBlock:
    type = "tool_use"

    def __init__(self, name, inp, id="tu_1"):
        self.name = name
        self.input = inp
        self.id = id


class FakeResp:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class FakeClient:
    """Devuelve respuestas predefinidas en secuencia y captura lo que recibe."""

    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = []

    class _Messages:
        def __init__(self, outer):
            self._outer = outer

        def create(self, **kwargs):
            self._outer.llamadas.append(kwargs)
            return self._outer._respuestas.pop(0)

    @property
    def messages(self):
        return FakeClient._Messages(self)


def _hist():
    return [{"role": "user", "content": "hola"}]


def test_respuesta_directa_sin_tools(monkeypatch):
    client = FakeClient([FakeResp("end_turn", [TextBlock("¡Hola! ¿en qué te ayudo?")])])
    monkeypatch.setattr(A, "get_client", lambda: client)
    out = A.responder(_hist(), {}, {})
    assert out == "¡Hola! ¿en qué te ayudo?"
    assert len(client.llamadas) == 1


def test_loop_ejecuta_tool_y_luego_responde(monkeypatch):
    client = FakeClient(
        [
            FakeResp("tool_use", [ToolUseBlock("ver_horarios", {"dias": 7})]),
            FakeResp("end_turn", [TextBlock("Tengo el martes a las 6.")]),
        ]
    )
    monkeypatch.setattr(A, "get_client", lambda: client)
    llamadas_tool = []
    monkeypatch.setattr(
        A, "ejecutar_tool", lambda n, a, c: llamadas_tool.append((n, a)) or '{"horarios": []}'
    )
    out = A.responder(_hist(), {}, {})
    assert out == "Tengo el martes a las 6."
    assert llamadas_tool == [("ver_horarios", {"dias": 7})]
    # 2da llamada al modelo lleva el turno assistant(tool_use) + user(tool_result).
    segunda = client.llamadas[1]["messages"]
    assert segunda[-1]["role"] == "user"
    assert segunda[-1]["content"][0]["type"] == "tool_result"


def test_tope_de_iteraciones(monkeypatch):
    # El modelo siempre pide tool → nunca contesta → debe cortar con fallback.
    siempre_tool = FakeResp("tool_use", [ToolUseBlock("ver_horarios", {})])
    client = FakeClient([siempre_tool] * 50)
    monkeypatch.setattr(A, "get_client", lambda: client)
    monkeypatch.setattr(A, "ejecutar_tool", lambda n, a, c: "{}")
    monkeypatch.setattr(A.settings, "max_iteraciones", 4)
    out = A.responder(_hist(), {}, {})
    assert out == A._FALLBACK
    assert len(client.llamadas) == 4


def test_sin_api_key_fallback(monkeypatch):
    monkeypatch.setattr(A, "get_client", lambda: None)
    assert A.responder(_hist(), {}, {}) == A._FALLBACK


def test_excepcion_en_create_fallback(monkeypatch):
    class Boom:
        @property
        def messages(self):
            class M:
                def create(self, **k):
                    raise RuntimeError("api caída")
            return M()

    monkeypatch.setattr(A, "get_client", lambda: Boom())
    assert A.responder(_hist(), {}, {}) == A._FALLBACK
