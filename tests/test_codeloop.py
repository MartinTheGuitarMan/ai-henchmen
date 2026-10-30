"""write_code retry loop: pure parts, and the loop itself with a fake backend and a fake sandbox."""
from __future__ import annotations

import sys
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
import code_loop  # noqa: E402
import code_run  # noqa: E402
import code_tasks  # noqa: E402

TASK = code_tasks.by_id("slugify")


class FakeSandbox:
    """Judges by marker text: 'GOOD' passes everything, 'HALF' passes the visible tests but not the held-out ones."""

    def __init__(self):
        self.calls = []

    def run(self, tid, code, tb="no"):
        self.calls.append((tid, tb))
        passes = "GOOD" in code or ("HALF" in code and tid.endswith("_vis"))
        return {"kind": "ok" if passes else "wrong_answer", "passed": 7 if passes else 3, "failed": 0 if passes else 4, "output":
                "" if passes else "= FAILURES =\nE assert 'a' == 'b'\n", "tail": ""}


@dataclass
class Cfg:
    name: str = "m"
    cloud: bool = True
    timeout: int = 60


def run_task(monkeypatch, replies, first, quiet=True):
    it = iter(replies)
    monkeypatch.setattr(code_loop.backends, "complete_ex", lambda cfg, msgs, schema, max_tokens=None: next(it))
    monkeypatch.setattr(code_loop.cr, "night_quiet", lambda host, win: (quiet, "") if quiet else (False, "closed"))
    monkeypatch.setattr(code_loop.cr, "night_model_ok", lambda host, win: (quiet, ""))
    args = Namespace(night_ssh="x", night_windows="", docker_host="x", min_timeout=60, max_tokens=100)
    ctx = code_loop.Ctx(Cfg(), "cloud", args, deadline=1e12)
    sb, entries = FakeSandbox(), {}
    monkeypatch.setattr(code_loop.cr, "sandbox_slot", fake_slot)
    r = code_loop.run_rounds(ctx, sb, [TASK], {"slugify": first}, entries, lambda: None)
    return r, entries["slugify"], sb


import contextlib


@contextlib.contextmanager
def fake_slot(host, timeout=0):
    yield True


def test_first_answer_accepted_needs_no_model_call(monkeypatch):
    r, entry, sb = run_task(monkeypatch, [], {"code": "GOOD", "failure": None})
    assert r == "done" and entry["accepted"] and len(entry["attempts"]) == 1
    assert ("slugify_vis", "short") in sb.calls and ("slugify", "no") in sb.calls and ("slugify_hold", "no") in sb.calls


def test_retry_feeds_back_visible_failures_and_stops_when_accepted(monkeypatch):
    seen = []
    it = iter([("```python\nGOOD\n```", "stop")])

    def fake(cfg, msgs, schema, max_tokens=None):
        seen.append(msgs)
        return next(it)
    monkeypatch.setattr(code_loop.backends, "complete_ex", fake)
    monkeypatch.setattr(code_loop.cr, "night_quiet", lambda host, win: (True, ""))
    monkeypatch.setattr(code_loop.cr, "night_model_ok", lambda host, win: (True, ""))
    monkeypatch.setattr(code_loop.cr, "sandbox_slot", fake_slot)
    args = Namespace(night_ssh="x", night_windows="", docker_host="x", min_timeout=60, max_tokens=100)
    entries = {}
    r = code_loop.run_rounds(code_loop.Ctx(Cfg(), "cloud", args, 1e12), FakeSandbox(), [TASK], {"slugify": {"code": "BAD", "failure": None}}, entries, lambda: None)
    entry = entries["slugify"]
    assert r == "done" and entry["accepted"] and len(entry["attempts"]) == 2
    last = seen[0][-1]["content"]
    assert seen[0][-2]["role"] == "assistant" and "BAD" in seen[0][-2]["content"]
    assert "assert 'a' == 'b'" in last          # failure text from the visible run


def test_gives_up_after_three_attempts_and_scores_the_last(monkeypatch):
    r, entry, _ = run_task(monkeypatch, [("```python\nBAD2\n```", "stop"), ("```python\nBAD3\n```", "stop")], {"code": "BAD", "failure": None})
    assert r == "done" and not entry["accepted"] and [a["code"].strip() for a in entry["attempts"]] == ["BAD", "BAD2", "BAD3"]
    assert entry["final"]["full"]["kind"] == "wrong_answer"


def test_unusable_first_answer_is_asked_again(monkeypatch):
    r, entry, _ = run_task(monkeypatch, [("```python\nGOOD\n```", "stop")], {"code": None, "failure": "truncated", "detail": "cap"})
    assert entry["accepted"] and len(entry["attempts"]) == 2


def test_closed_window_defers_and_runs_nothing(monkeypatch):
    r, entry, sb = run_task(monkeypatch, [], {"code": "BAD", "failure": None}, quiet=False)
    assert r == "deferred" and sb.calls == []
    # Cfg is a cloud model here, so the sandbox check (not the model gate) is what holds it back


def test_verdict_rules():
    v = code_loop.verdict
    assert v(14, 18, 20, 18, True)[0] == "PASS"
    assert v(24, 25, 25, 25, True)[0] == "NO-NEED"
    assert v(4, 6, 25, 15, True)[0] == "FAIL"          # trust 60%
    assert v(11, 12, 20, 20, True)[0] == "FAIL"        # trust fine, lift +1
    assert v(11, 20, 0, 0, True)[0] == "FAIL"          # nothing accepted
    assert v(11, 20, 5, 5, False)[0] == "not run"


def test_split_tests_deals_functions_alternately():
    vis, hold = code_tasks.split_tests("import x\n\ndef helper():\n    pass\n\ndef test_a():\n    pass\n\ndef test_b():\n    pass\n\ndef test_c():\n    pass\n")
    assert "test_a" in vis and "test_c" in vis and "test_b" not in vis and "helper" in vis
    assert "test_b" in hold and "test_a" not in hold and "helper" in hold


def test_all_reference_solutions_pass_both_halves():
    import subprocess, tempfile
    for t in code_tasks.TASKS[:3]:
        for half in code_tasks.split_tests(t["tests"]):
            d = Path(tempfile.mkdtemp())
            (d / "solution.py").write_text(t["reference"])
            (d / "test_task.py").write_text(half)
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_task.py"], cwd=d, capture_output=True)
            assert r.returncode == 0


def test_window_helpers_and_night_floor(monkeypatch):
    from datetime import datetime
    assert code_run.minutes_left("22:00-23:00,06:00-07:00", datetime(2026, 10, 30, 22, 50)) == 10
    assert code_run.minutes_left("22:00-23:00", datetime(2026, 10, 30, 12, 0)) == 0
    monkeypatch.setattr(code_run, "in_windows", lambda spec, now=None: True)
    assert code_run.floor_pct_now(True, "x") == 10 and code_run.floor_pct_now(False, "x") == 25
    monkeypatch.setattr(code_run, "in_windows", lambda spec, now=None: False)
    assert code_run.floor_pct_now(True, "x") == 25            # outside the windows the margin stays at 25


def test_night_models_stop_before_the_window_closes(monkeypatch):
    monkeypatch.setattr(code_run, "night_quiet", lambda host, win: (True, ""))
    monkeypatch.setattr(code_run, "minutes_left", lambda spec, now=None: 5.0)
    ok, why = code_run.night_model_ok("host", "x")
    assert not ok and "end of the window" in why
    monkeypatch.setattr(code_run, "minutes_left", lambda spec, now=None: 30.0)
    assert code_run.night_model_ok("host", "x")[0]


def test_model_and_sandbox_never_overlap(tmp_path):
    a, b = code_run.NightExclusive(str(tmp_path / "l")), code_run.NightExclusive(str(tmp_path / "l"))
    assert a.acquire(1)
    assert not b.acquire(0)          # a sandbox run (or a second model) must wait while the first holds the night host
    a.release()
    assert b.acquire(1)
    b.release()
