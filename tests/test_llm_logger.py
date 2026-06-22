from types import SimpleNamespace

from agente.llm_logger import content_to_text, render_llm_request, render_llm_response


def test_render_request_textualiza_system_y_mensajes():
    text = render_llm_request(
        system=[{"type": "text", "text": "Eres asistente."}],
        messages=[
            {"role": "user", "content": "hola"},
            {
                "role": "assistant",
                "content": [SimpleNamespace(type="tool_use", name="ver_horarios", input={"dias": 7})],
            },
        ],
    )

    assert "SYSTEM" in text
    assert "Eres asistente." in text
    assert "[user]" in text
    assert "hola" in text
    assert "[tool_use ver_horarios]" in text
    assert '"dias": 7' in text


def test_render_response_textualiza_text_blocks():
    resp = SimpleNamespace(content=[SimpleNamespace(type="text", text="Respuesta final.")])
    assert render_llm_response(resp) == "Respuesta final."


def test_content_to_text_tool_result():
    text = content_to_text([{"type": "tool_result", "tool_use_id": "tu_1", "content": "sin horarios"}])
    assert "[tool_result tu_1]" in text
    assert "sin horarios" in text
