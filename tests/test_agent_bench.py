"""bench/agent_run.py against tests/fake_gemini.py: gen docs in code_run's format, no real CLI."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bench"))
import agent_run  # noqa: E402
import code_tasks  # noqa: E402

FAKE = Path(__file__).with_name("fake_gemini.py")


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    bindir = Path(sys.executable).parent
    monkeypatch.setenv("PATH", f"{bindir}:{__import__('os').environ.get('PATH', '')}")
    cfg = tmp_path / "agents.json"
    cfg.write_text(json.dumps({"gemini": {"command": str(FAKE)}}))
    monkeypatch.setenv("MINION_AGENTS_CONFIG", str(cfg))
    monkeypatch.setenv("MINION_PRIVACY_MAP", str(tmp_path / "real-map-must-not-be-used.json"))


def _task(tid):
    return next(t for t in code_tasks.TASKS if t["id"] == tid)


def test_solution_becomes_gen_record(monkeypatch, tmp_path):
    ref = _task("merge_intervals")["reference"]
    monkeypatch.setenv("FAKE_GEMINI_MODE", "solve")
    monkeypatch.setenv("FAKE_SOLUTION", ref)
    out = tmp_path / "run"
    assert agent_run.main(["--out", str(out), "--tasks", "merge_intervals", "--pause", "0"]) == 0
    doc = json.loads((out / "gen" / "gemini-cli-agent.json").read_text())
    rec = doc["tasks"]["merge_intervals"]
    assert doc["kind"] == "agent" and rec["agent_status"] == "ok"
    assert rec["code"] == ref and rec["failure"] is None
    assert rec["files"] == ["solution.py"] and rec["outside_own_files"] == []
    assert not (tmp_path / "real-map-must-not-be-used.json").exists()


def test_fix_task_starts_from_buggy_code_and_flags_outside_files(monkeypatch, tmp_path):
    fix = next(t for t in code_tasks.TASKS if t["kind"] == "fix")
    monkeypatch.setenv("FAKE_GEMINI_MODE", "solve")
    monkeypatch.setenv("FAKE_SOLUTION", fix["buggy"])
    monkeypatch.setenv("FAKE_EXTRA", "notes.txt")
    out = tmp_path / "run"
    agent_run.main(["--out", str(out), "--tasks", fix["id"], "--pause", "0"])
    rec = json.loads((out / "gen" / "gemini-cli-agent.json").read_text())["tasks"][fix["id"]]
    assert rec["note"] == "solution.py unchanged"
    assert rec["outside_own_files"] == ["notes.txt"]


def test_agent_failure_is_a_generation_error_and_resume_skips_done(monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_GEMINI_MODE", "error")
    out = tmp_path / "run"
    agent_run.main(["--out", str(out), "--tasks", "slugify", "--pause", "0"])
    rec = json.loads((out / "gen" / "gemini-cli-agent.json").read_text())["tasks"]["slugify"]
    assert rec["error"] == "AGENT_CLI_ERROR" and "code" not in rec
    monkeypatch.setenv("FAKE_GEMINI_MODE", "solve")
    monkeypatch.setenv("FAKE_SOLUTION", "x = 1\n")
    agent_run.main(["--out", str(out), "--tasks", "slugify", "--pause", "0"])
    assert json.loads((out / "gen" / "gemini-cli-agent.json").read_text())["tasks"]["slugify"]["error"] == "AGENT_CLI_ERROR"


def test_task_text_drops_fence_rule_and_keeps_buggy_code():
    fix = next(t for t in code_tasks.TASKS if t["kind"] == "fix")
    text = agent_run.task_text(fix)
    assert code_tasks.FENCE_RULE not in text and "solution.py" in text
    assert fix["buggy"].strip().splitlines()[0] in text


def test_report_reads_agent_gen_doc(monkeypatch, tmp_path):
    import code_report
    monkeypatch.setenv("FAKE_GEMINI_MODE", "solve")
    monkeypatch.setenv("FAKE_SOLUTION", _task("slugify")["reference"])
    out = tmp_path / "run"
    agent_run.main(["--out", str(out), "--tasks", "slugify", "--pause", "0"])
    rows = code_report.load(out)
    assert rows[0]["model"] == "gemini-cli-agent" and rows[0]["per"]["slugify"]["failure"] == "not_run"


def test_task_md_change_counts_as_outside(monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_GEMINI_MODE", "solve")
    monkeypatch.setenv("FAKE_SOLUTION", "x = 1\n")
    monkeypatch.setenv("FAKE_EXTRA", "TASK.md")
    out = tmp_path / "run"
    agent_run.main(["--out", str(out), "--tasks", "slugify", "--pause", "0"])
    rec = json.loads((out / "gen" / "gemini-cli-agent.json").read_text())["tasks"]["slugify"]
    assert rec["outside_own_files"] == ["TASK.md"]


def test_busy_is_not_recorded_and_stops(monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_GEMINI_MODE", "503")
    out = tmp_path / "run"
    agent_run.main(["--out", str(out), "--tasks", "slugify,merge_intervals", "--pause", "0"])
    assert json.loads((out / "gen" / "gemini-cli-agent.json").read_text())["tasks"] == {}
