"""Unit tests for the coding bench (bench/code_*.py, bench/sandbox.py). No model and, by default, no Docker needed.

The sandbox self-test runs a real known-bad snippet and needs Docker: set CODEBENCH_DOCKER_HOST to the ssh name of the
machine that runs it (or have docker locally with the minions-codebench:1 image). Without it that test is skipped.
Everything that executes here is our own reference code, never model output.
"""
import json
import os
import re
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bench"))
import code_report  # noqa: E402
import code_run  # noqa: E402
import code_tasks  # noqa: E402
import sandbox  # noqa: E402
from minions.config import Config  # noqa: E402

TASKS = code_tasks.TASKS
IDS = [t["id"] for t in TASKS]


def pytest_run(tmp_path: Path, code: str, tests: str) -> subprocess.CompletedProcess:
    (tmp_path / "solution.py").write_text(code)
    (tmp_path / "test_task.py").write_text(tests)
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_task.py"], cwd=tmp_path,
                          capture_output=True, text=True, timeout=60, env={**os.environ, "PYTHONPATH": str(tmp_path)})


# ---------------------------------------------------------------- the tasks
def test_task_set_shape():
    basic = [t for t in TASKS if t["level"] != "complex"]
    complex_ = [t for t in TASKS if t["level"] == "complex"]
    assert 15 <= len(basic) <= 18 and 6 <= len(complex_) <= 8
    assert len(set(IDS)) == len(IDS)
    kinds = [t["kind"] for t in basic]
    assert kinds.count("fix") in (3, 4) and 2 <= kinds.count("regex") <= 3
    assert {t["level"] for t in basic} == {"easy", "medium", "hard"}
    assert 2 <= sum(t["level"] == "hard" for t in basic) <= 4
    assert any(t["kind"] == "fix" for t in complex_)
    assert max(len(t["prompt"].splitlines()) for t in complex_) >= 30      # at least one task is a 30+ line spec


@pytest.mark.parametrize("t", TASKS, ids=IDS)
def test_prompt_hides_the_tests_and_asks_for_one_block(t):
    assert "def test_" not in t["prompt"] and "assert " not in t["prompt"]
    assert "exactly one fenced" in t["prompt"]
    assert t["n_tests"] >= 4


@pytest.mark.parametrize("t", TASKS, ids=IDS)
def test_reference_solution_passes_every_hidden_test(t, tmp_path):
    r = pytest_run(tmp_path, t["reference"], t["tests"])
    assert r.returncode == 0, r.stdout[-1500:]
    assert re.search(rf"\b{t['n_tests']} passed\b", r.stdout), (t["n_tests"], r.stdout[-300:])


@pytest.mark.parametrize("t", [t for t in TASKS if t["kind"] == "fix"], ids=lambda t: t["id"])
def test_buggy_code_fails_some_tests_but_not_all(t, tmp_path):
    r = pytest_run(tmp_path, t["buggy"], t["tests"])
    m = re.search(r"(\d+) failed", r.stdout)
    assert m and 0 < int(m[1]) <= t["n_tests"], r.stdout[-500:]
    assert t["level"] == "complex" or t["buggy"].strip() in t["prompt"]


def test_wrong_solution_scores_partial(tmp_path):
    t = code_tasks.by_id("slugify")
    r = pytest_run(tmp_path, "def slugify(t):\n    return t.lower().replace(' ', '-')\n", t["tests"])
    assert r.returncode != 0 and re.search(r"\d+ passed", r.stdout) and "failed" in r.stdout


# ---------------------------------------------------------------- code extraction
def test_extract_plain_block():
    e = code_run.extract_code("Here you go:\n```python\ndef f():\n    return 1\n```\nDone.")
    assert e["failure"] is None and e["code"].startswith("def f")


def test_extract_takes_first_python_block_and_strips_thinking():
    raw = "<think>```python\nnot this\n```</think>\n```python\nx = 1\n```\n```python\ny = 2\n```"
    e = code_run.extract_code(raw)
    assert e["code"].strip() == "x = 1" and e["blocks"] == 2


def test_extract_untagged_block_accepted_other_languages_not():
    assert code_run.extract_code("```\nx = 1\n```")["failure"] is None
    assert code_run.extract_code("```bash\nls\n```")["failure"] == "no_code_block"


def test_extract_no_fence_is_a_failure_even_if_it_is_code():
    assert code_run.extract_code("def f():\n    return 1")["failure"] == "no_code_block"


def test_extract_truncated_cases():
    assert code_run.extract_code("```python\ndef f():\n    retu", "length")["failure"] == "truncated"
    assert code_run.extract_code("```python\ndef f():\n    retu")["failure"] == "truncated"        # fence never closed
    assert code_run.extract_code("<think>still thinking about it", "length")["failure"] == "truncated"
    assert code_run.extract_code("", "length")["failure"] == "truncated"


def test_extract_syntax_error_is_caught_without_running():
    e = code_run.extract_code("```python\ndef f(:\n  pass\n```")
    assert e["failure"] == "syntax_error" and "SyntaxError" in e["detail"]


def test_score():
    t = code_tasks.by_id("slugify")
    ok = code_run.score(t, {"failure": None}, {"kind": "ok", "passed": t["n_tests"]})
    assert ok["solved"] and ok["failure"] is None
    part = code_run.score(t, {"failure": None}, {"kind": "wrong_answer", "passed": 3})
    assert not part["solved"] and part["passed"] == 3 and part["failure"] == "wrong_answer"
    assert code_run.score(t, {"failure": "no_code_block"}, None)["passed"] == 0
    assert code_run.score(t, {"failure": None}, None)["failure"] == "not_run"
    assert code_run.score(t, {"failure": None}, {"kind": "timeout", "passed": 2})["failure"] == "timeout"


# ---------------------------------------------------------------- the sandbox command and parsing (no docker)
def test_docker_command_has_every_restriction():
    a = sandbox.run_args("codebench-x", "/stage/test_slugify.py")
    j = " ".join(a)
    assert a[:2] == ["run", "--rm"]
    for flag in ("--network none", "--read-only", "--cap-drop ALL", "--security-opt no-new-privileges", "--user 65534:65534",
                 "--cpus 1", "--memory 256m", "--memory-swap 256m", "--pids-limit 64"):
        assert flag in j, flag
    assert "/work:rw,noexec,nosuid,size=16m" in j
    mounts = [a[i + 1] for i, x in enumerate(a) if x in ("-v", "--volume", "--mount")]
    assert mounts == ["/stage/test_slugify.py:/tests/test_task.py:ro"]          # the only host mount, read-only
    assert "--privileged" not in j and "--network host" not in j
    assert "timeout -k 1 10 python" in a[-1]


def test_unsafe_task_ids_are_refused():
    for bad in ("../x", "a b", "x;rm", "", "X", "a" * 60):
        with pytest.raises(ValueError):
            sandbox.safe_id(bad)


def test_remote_commands_go_through_ssh_and_never_local_docker():
    sb = sandbox.Sandbox("somehost")
    cmd = sb._cmd(["run", "x"])
    assert cmd[0] == "ssh" and "somehost" in cmd and "docker run x" in cmd[-1]
    assert sandbox.Sandbox(None)._cmd(["ps"]) == ["docker", "ps"]


def test_parse_pytest_and_classify():
    out = ("../tests/test_task.py::test_a PASSED  [ 50%]\n../tests/test_task.py::test_b FAILED  [100%]\n")
    p = sandbox.parse_pytest(out)
    assert (p["passed"], p["failed"]) == (1, 1)
    assert sandbox.classify(1, 0.5, p, out) == "wrong_answer"
    ok = sandbox.parse_pytest("/tests/test_task.py::test_a PASSED\n")
    assert sandbox.classify(0, 0.5, ok, "x") == "ok"
    col = sandbox.parse_pytest("ERROR collecting test_task.py\nImportError: cannot import name 'f'\n")
    assert sandbox.classify(2, 0.3, col, "ERROR collecting") == "import_error"
    assert sandbox.classify(124, 10.2, ok, "x") == "timeout"
    assert sandbox.classify(137, 10.4, ok, "x") == "timeout"
    assert sandbox.classify(137, 1.2, ok, "x") == "killed"
    assert sandbox.classify(125, 0.1, ok, "") == "sandbox_error"


def test_printed_fake_results_do_not_reach_the_output():
    # pytest captures what the solution prints; this checks the parser only counts well-formed pytest lines
    p = sandbox.parse_pytest("all tests PASSED\n10 passed\n")
    assert p["passed"] == 0


# ---------------------------------------------------------------- generation with a fake backend
def fake_cfg(name="fake-cloud", cloud=True):
    return Config(backend="openai-compat", base_url="http://example.invalid/v1", model="m", name=name, cloud=cloud, timeout=5)


def test_generate_one_records_code_latency_and_failure(monkeypatch):
    replies = iter([("```python\ndef f():\n    return 1\n```", "stop"), ("I cannot write that.", "stop"), ("```python\ndef f(\n```", "stop")])
    monkeypatch.setattr(code_run.backends, "complete_ex", lambda cfg, msgs, schema, max_tokens=None: next(replies))
    t = code_tasks.by_id("slugify")
    a, b, c = (code_run.generate_one(fake_cfg(), t) for _ in range(3))
    assert a["code"].strip().startswith("def f") and a["failure"] is None and a["latency"] >= 0
    assert b["failure"] == "no_code_block" and c["failure"] == "syntax_error"


def test_prompt_is_one_shot_with_no_schema_and_temperature_not_overridden(monkeypatch):
    seen = {}

    def fake(cfg, msgs, schema, max_tokens=None):
        seen.update(msgs=msgs, schema=schema, max_tokens=max_tokens)
        return "```python\nx=1\n```", "stop"
    monkeypatch.setattr(code_run.backends, "complete_ex", fake)
    code_run.generate_one(fake_cfg(), code_tasks.by_id("slugify"))
    assert seen["schema"] is None and [m["role"] for m in seen["msgs"]] == ["system", "user"]
    assert seen["max_tokens"] == code_run.MAX_TOKENS


def test_backend_error_is_recorded_not_raised(monkeypatch):
    from minions.errors import BackendError

    def boom(*a, **k):
        raise BackendError("HTTP 500")
    monkeypatch.setattr(code_run.backends, "complete_ex", boom)
    r = code_run.generate_one(fake_cfg(), code_tasks.by_id("slugify"))
    assert r["error"] == "MINION_BACKEND_ERROR"


class FakeSandbox:
    def __init__(self):
        self.calls = []

    def stage(self, tests):
        self.staged = list(tests)

    def run(self, task_id, code):
        self.calls.append((task_id, code))
        n = code_tasks.by_id(task_id)["n_tests"]
        return {"kind": "ok", "passed": n, "failed": 0, "elapsed": 0.1, "rc": 0}


def test_whole_pipeline_with_fakes_and_report(monkeypatch, tmp_path):
    monkeypatch.setattr(code_run.backends, "complete_ex",
                        lambda cfg, msgs, schema, max_tokens=None: ("```python\n" + code_tasks.by_id("slugify")["reference"] + "```", "stop"))
    out = tmp_path / "run"
    (out / "gen").mkdir(parents=True)
    tasks = [code_tasks.by_id("slugify"), code_tasks.by_id("flatten_dict")]
    args = Namespace(redo=False, redo_exec=False, night_ssh="", night_windows="00:00-00:00", docker_host=None, max_tokens=100, min_timeout=180, only=None)
    code_run.work_group([fake_cfg()], "local", out, tasks, args, deadline=1e12)
    gen = json.loads((out / "gen" / "fake-cloud.json").read_text())
    assert set(gen["tasks"]) == {"slugify", "flatten_dict"} and gen["cloud"] is True
    code_run.STATE["gen_done"] = True
    monkeypatch.setattr(code_run.sandbox, "selftest", lambda sb: {"ok": True})
    sb = FakeSandbox()
    code_run.execute_loop(sb, out, tasks, args, deadline=1e12)
    assert [c[0] for c in sb.calls] == ["slugify", "flatten_dict"] and sb.staged == ["slugify", "flatten_dict"]
    assert code_run.STATE["sandbox_ok"] is True
    # a rerun neither generates nor executes again (resume)
    code_run.work_group([fake_cfg()], "local", out, tasks, args, deadline=1e12)
    code_run.execute_loop(sb, out, tasks, args, deadline=1e12)
    assert len(sb.calls) == 2
    rows = code_report.load(out)
    assert code_report.summary(rows[0])["solved"] == 2
    (out / "notes.json").write_text(json.dumps({"notes": ["x: decision model"], "models": ["fake-cloud"]}))
    (out / "HYPOTHESIS.md").write_text("We guessed before.")
    code_report.main(out)


def test_failed_selftest_runs_nothing(monkeypatch, tmp_path):
    out = tmp_path / "run"
    (out / "gen").mkdir(parents=True)
    (out / "gen" / "m.json").write_text(json.dumps({"model": "m", "tasks": {"slugify": {"code": "x = 1\n", "failure": None}}}))
    monkeypatch.setattr(code_run.sandbox, "selftest", lambda sb: {"ok": False})
    sb = FakeSandbox()
    args = Namespace(redo=False, redo_exec=False, night_ssh="", night_windows="", docker_host=None)
    code_run.execute_loop(sb, out, [code_tasks.by_id("slugify")], args, deadline=1e12)
    assert sb.calls == [] and code_run.STATE["sandbox_ok"] is False


def test_text_models_leaves_out_decision_models_and_duplicates():
    from minions.config import Roster
    r = Roster.from_dict({"models": {
        "a": {"backend": "ollama", "base_url": "http://127.0.0.1:1/v1", "model": "m1"},
        "a-judge": {"backend": "ollama", "base_url": "http://127.0.0.1:1/v1", "model": "m1", "kind": "reasoning"},
        "d": {"backend": "systemone", "kind": "decision", "model": "j", "base_url": "http://127.0.0.1:2/v1"},
        "b": {"backend": "ollama", "base_url": "http://127.0.0.1:1/v1", "model": "m2"}}})
    models, notes = code_run.text_models(r)
    assert [m.name for m in models] == ["a", "b"] and len(notes) == 2


def test_night_gate_window_and_cloud_free(monkeypatch):
    assert code_run.night_quiet("", "03:00-04:00") == (True, "")          # docker on this machine: nothing to disturb
    monkeypatch.setattr(code_run, "in_windows", lambda spec, now=None: False)
    ok, why = code_run.night_quiet("somehost", "22:00-23:00")
    assert not ok and "outside" in why
    monkeypatch.setattr(code_run, "in_windows", lambda spec, now=None: True)
    monkeypatch.setattr(code_run, "jobs_running", lambda host: ["123 nightly.sh"])
    assert not code_run.night_quiet("somehost", "x")[0]
    monkeypatch.setattr(code_run, "jobs_running", lambda host: None)
    assert not code_run.night_quiet("somehost", "x")[0]                   # cannot ask: treated as busy
    monkeypatch.setattr(code_run, "jobs_running", lambda host: [])
    assert code_run.night_quiet("somehost", "x")[0]


# ---------------------------------------------------------------- the real sandbox (needs docker)
def _sandbox_or_skip():
    sb = sandbox.Sandbox(os.environ.get("CODEBENCH_DOCKER_HOST") or None)
    try:
        sb.check()
    except sandbox.SandboxUnavailable as e:
        pytest.skip(f"no docker sandbox: {e}")
    return sb


def test_sandbox_selftest_known_bad_snippet_is_blocked():
    res = sandbox.selftest(_sandbox_or_skip())
    assert res["probes_blocked"], res                # network, writes, root, host paths, pids, disk, environment: all blocked
    assert res["infinite_loop_killed"] and res["memory_hog_killed"] and res["good_snippet_passes"], res


def test_sandbox_scores_a_real_task_and_a_wrong_one():
    sb = _sandbox_or_skip()
    t = code_tasks.by_id("slugify")
    sb.stage({"slugify": t["tests"]})
    good = sb.run("slugify", t["reference"])
    assert good["kind"] == "ok" and good["passed"] == t["n_tests"]
    bad = sb.run("slugify", "import re\ndef slugify(t):\n    return re.sub('[^a-z0-9]+', '-', t.lower()).strip('-')\n")
    assert bad["kind"] == "wrong_answer" and 0 < bad["passed"] < t["n_tests"]
    missing = sb.run("slugify", "def other():\n    pass\n")
    assert missing["kind"] == "import_error" and missing["passed"] == 0
