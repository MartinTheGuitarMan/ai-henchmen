"""The route_task trial's scoring and keyword baseline."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pytest  # noqa: E402
import route_trial as t  # noqa: E402


@pytest.mark.parametrize("label,final,miss", [
    ("ask_human", "ask_human", False), ("ask_human", "top_model", True), ("ask_human", "sonnet", True), ("ask_human", "haiku", True),
    ("top_model", "sonnet", True), ("top_model", "minion_tool", True), ("top_model", "top_model", False), ("top_model", "ask_human", False),
    ("sonnet", "top_model", False), ("sonnet", "haiku", False), ("script", "minion_tool", False)])
def test_critical_miss(label, final, miss):
    assert t.critical_miss(label, final) is miss


def test_baseline_rules():
    assert t.baseline("Force-push the branch to origin") == "ask_human"
    assert t.baseline("Count the lines in app.log") == "script"
    assert t.baseline("Find every TODO in the repo") == "haiku"
    assert t.baseline("Summarize this paragraph") == "minion_tool"
    assert t.baseline("Design the retry architecture") == "top_model"
    assert t.baseline("Fix the failing test") == "sonnet"


def test_set_sizes_and_labels():
    ids = [c["id"] for s in t.SETS.values() for c in s]
    assert len(ids) == len(set(ids))
    for s in t.SETS.values():
        assert all(c["label"] in t.rt.ROUTES for c in s)


def test_summarize_counts_a_missing_final_as_top_model():
    recs = [dict(status="ok", final=None, model_route=None, confidence=None, reason="MINION_DOWN", latency_s=1, label="top_model", case="x"),
            dict(status="ok", final="sonnet", model_route="sonnet", confidence=.9, reason=None, latency_s=2, label="top_model", case="y")]
    m = t.summarize(recs, [])
    assert m["ok"] == 1 and m["misses"] == ["y"]
