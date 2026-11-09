"""Managed native Ollama models send the context they were loaded with; unmanaged ones do not."""
from dataclasses import replace

from minions import backends
from minions.config import Config


def _cfg(**kw) -> Config:
    base = dict(name="m", backend="ollama", base_url="http://127.0.0.1:1/v1", model="x", ollama_native=True)
    base.update(kw)
    return Config(**base)


def _capture(monkeypatch) -> list:
    seen = []
    monkeypatch.setattr(backends, "_post", lambda cfg, url, payload: (seen.append((url, payload)),
                        {"message": {"content": "ok"}, "done_reason": "stop"})[1])
    monkeypatch.setattr(backends.tokens, "note", lambda *a, **k: None)
    return seen


def test_managed_sends_num_ctx(monkeypatch):
    seen = _capture(monkeypatch)
    backends.complete_ex(_cfg(manage=True, context=24576), [{"role": "user", "content": "hi"}], max_tokens=100)
    assert seen[0][1]["options"]["num_ctx"] == 24576
    assert seen[0][1]["options"]["num_predict"] == 100


def test_unmanaged_leaves_context_alone(monkeypatch):
    seen = _capture(monkeypatch)
    backends.complete_ex(_cfg(), [{"role": "user", "content": "hi"}])
    assert "num_ctx" not in seen[0][1]["options"]


def test_think_false_is_sent_only_when_set(monkeypatch):
    seen = _capture(monkeypatch)
    backends.complete_ex(_cfg(think=False), [{"role": "user", "content": "hi"}])
    backends.complete_ex(_cfg(), [{"role": "user", "content": "hi"}])
    assert seen[0][1]["think"] is False
    assert "think" not in seen[1][1]
