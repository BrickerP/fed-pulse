import io
import json

from fed_pulse import llm
from fed_pulse.heuristic import assess


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_generate_brief_uses_text_blocks_and_model(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=0):
        seen["body"] = json.loads(req.data)
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        payload = {"content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "Pressure is high."}]}
        return _Resp(json.dumps(payload).encode())

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    out = llm.generate_brief(None, None, assess(None, None), api_key="test-key", model="my-model")
    assert out == "Pressure is high."
    assert seen["body"]["model"] == "my-model"
    assert seen["headers"]["x-api-key"] == "test-key"
    assert seen["headers"]["anthropic-version"] == llm.API_VERSION
