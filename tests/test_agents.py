"""Gemini CLI agent: run against tests/fake_gemini.py, never the real CLI."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agents import config as acfg
from agents.gemini_cli import cap_response, parse_output, run_task

FAKE = Path(__file__).with_name("fake_gemini.py")


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _init(path: Path) -> None:
    git("init", "-q", "-b", "main", cwd=path)
    git("config", "user.email", "t@example.invalid", cwd=path)
    git("config", "user.name", "t", cwd=path)


@pytest.fixture
def remote(tmp_path):
    r = tmp_path / "remote.git"
    r.mkdir()
    git("init", "-q", "--bare", "-b", "main", cwd=r)
    return r


@pytest.fixture
def repo(tmp_path, remote):
    r = tmp_path / "repo"
    r.mkdir()
    _init(r)
    (r / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (r / "test_calc.py").write_text("from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    git("add", "-A", cwd=r)
    git("commit", "-qm", "init", cwd=r)
    git("remote", "add", "origin", str(remote), cwd=r)
    git("push", "-q", "origin", "main", cwd=r)
    return r


@pytest.fixture
def low_map(tmp_path, repo, monkeypatch):
    p = tmp_path / "privacy-map.json"
    p.write_text(json.dumps({"version": 1, "default": "personal", "paths": [{"path": str(repo), "class": "low"}]}))
    monkeypatch.setenv("MINION_PRIVACY_MAP", str(p))
    return p


@pytest.fixture
def conf(tmp_path, low_map):
    return acfg.AgentConfig(
        gemini=acfg.GeminiSettings(command=str(FAKE), timeout_s=10, max_response_chars=1000),
        runs_dir=tmp_path / "runs",
    )


@pytest.fixture(autouse=True)
def _python_for_fake(monkeypatch):
    # fake_gemini.py runs with whatever python3 is on PATH; make sure it is this interpreter's.
    bindir = Path(sys.executable).parent
    monkeypatch.setenv("PATH", f"{bindir}:{__import__('os').environ.get('PATH', '')}")


def test_ok_run_gives_patch_and_leaves_repo_alone(repo, conf, monkeypatch, tmp_path):
    argv_out = tmp_path / "argv.json"
    monkeypatch.setenv("FAKE_GEMINI_MODE", "ok")
    monkeypatch.setenv("FAKE_ARGV_OUT", str(argv_out))
    before = git("rev-parse", "HEAD", cwd=repo)
    res = run_task("add sub()", repo, conf=conf, test_command=f"{sys.executable} -m pytest -q -p no:cacheprovider")
    assert res.status == "ok", res.message
    assert res.summary == "Added sub to calc.py and new_file.txt."
    patch = Path(res.patch_path).read_text()
    assert "def sub" in patch and "new_file.txt" in patch
    assert git("rev-parse", "HEAD", cwd=repo) == before
    assert git("status", "--porcelain", cwd=repo) == ""
    assert git("remote", cwd=Path(res.clone_path)).strip() == ""
    subprocess.run(["git", "apply", "--check", res.patch_path], cwd=repo, check=True)
    seen = json.loads(argv_out.read_text())
    argv = seen["argv"]
    assert "--yolo" not in argv and "yolo" not in argv
    assert "--sandbox" in argv and "--policy" in argv and "--skip-trust" in argv
    assert Path(argv[argv.index("--policy") + 1]).is_file()
    assert argv[argv.index("--approval-mode") + 1] == "auto_edit"
    assert Path(seen["cwd"]).resolve() == Path(res.clone_path).resolve()
    assert "=== TASK ===\nadd sub()" in seen["prompt"]
    assert res.tests["passed"] is True


def test_reviewer_role_uses_default_approval(repo, conf, monkeypatch, tmp_path):
    argv_out = tmp_path / "argv.json"
    monkeypatch.setenv("FAKE_GEMINI_MODE", "ok")
    monkeypatch.setenv("FAKE_ARGV_OUT", str(argv_out))
    run_task("review", repo, role="codereviewer", conf=conf)
    argv = json.loads(argv_out.read_text())["argv"]
    assert argv[argv.index("--approval-mode") + 1] == "default"


def test_agent_commits_are_still_in_patch(repo, conf, monkeypatch):
    monkeypatch.setenv("FAKE_GEMINI_MODE", "commit")
    res = run_task("add sub()", repo, conf=conf)
    assert res.status == "ok"
    assert res.agent_commits and "agent commit" in res.agent_commits[0]
    assert "def sub" in Path(res.patch_path).read_text()


def test_no_privacy_map_refuses(repo, conf, monkeypatch, tmp_path):
    monkeypatch.setenv("MINION_PRIVACY_MAP", str(tmp_path / "missing.json"))
    res = run_task("x", repo, conf=conf)
    assert res.status == "refused" and "'personal'" in res.message
    assert not conf.runs_dir.exists()


def test_personal_repo_refuses(repo, conf, low_map):
    low_map.write_text(json.dumps({"version": 1, "default": "personal",
                                   "paths": [{"path": str(repo), "class": "personal"}]}))
    assert run_task("x", repo, conf=conf).status == "refused"


def test_unpushed_base_refuses_unless_listed(repo, conf, monkeypatch):
    monkeypatch.setenv("FAKE_GEMINI_MODE", "ok")
    (repo / "local.txt").write_text("not pushed\n")
    git("add", "-A", cwd=repo)
    git("commit", "-qm", "local only", cwd=repo)
    res = run_task("x", repo, conf=conf)
    assert res.status == "refused" and "not yet public" in res.message
    # an older, pushed base is fine
    assert run_task("x", repo, base_ref="origin/main", conf=conf).status == "ok"
    conf.unpushed_ok_repos = [repo.resolve()]
    assert run_task("x", repo, conf=conf).status == "ok"


def test_bad_inputs_refused(repo, conf, tmp_path):
    assert run_task("x", tmp_path / "nowhere", conf=conf).status == "refused"
    assert run_task("x", repo, role="boss", conf=conf).status == "refused"
    assert run_task("  ", repo, conf=conf).status == "refused"
    assert run_task("x", repo, base_ref="--upload-pack=evil", conf=conf).status == "refused"
    assert run_task("x", repo, base_ref="no-such-branch", conf=conf).status == "refused"


def test_missing_binary_refused(repo, conf):
    conf.gemini.command = "definitely-not-gemini"
    res = run_task("x", repo, conf=conf)
    assert res.status == "refused" and "not found" in res.message


@pytest.mark.parametrize("mode,status", [("429", "rate_limited"), ("503", "busy"), ("error", "cli_error"), ("turns", "turn_limit")])
def test_failure_modes(repo, conf, monkeypatch, mode, status):
    monkeypatch.setenv("FAKE_GEMINI_MODE", mode)
    res = run_task("x", repo, conf=conf)
    assert res.status == status, res.message
    if mode == "error":
        assert "boom" in res.message


def test_timeout_kills(repo, conf, monkeypatch):
    monkeypatch.setenv("FAKE_GEMINI_MODE", "sleep")
    conf.gemini.timeout_s = 1
    t = time.monotonic()
    assert run_task("x", repo, conf=conf).status == "timeout"
    assert time.monotonic() - t < 15


def test_long_output_capped_to_summary(repo, conf, monkeypatch):
    monkeypatch.setenv("FAKE_GEMINI_MODE", "long")
    assert run_task("x", repo, conf=conf).response == "short"


def test_cap_without_summary():
    text, summary = cap_response("y" * 5000, 1000)
    assert summary is None and len(text) < 1000 and "over the 1000 limit" in text


def test_parse_output_recovers_error_after_prologue():
    resp, stats, err = parse_output("", 'Loaded creds.\n{"error": {"code": 403, "message": "nope"}}')
    assert resp == "" and err == {"code": 403, "message": "nope"}


def test_config_load(tmp_path, repo):
    p = tmp_path / "agents.json"
    p.write_text(json.dumps({"gemini": {"model": "some-model", "timeout_s": 60}, "unpushed_ok_repos": [str(repo)]}))
    c = acfg.load(p)
    assert c.gemini.model == "some-model" and c.gemini.timeout_s == 60 and c.unpushed_ok(repo)
    assert acfg.load(tmp_path / "missing.json").unpushed_ok_repos == []


def test_policy_file_parses_and_denies_remotes():
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib
    from agents.gemini_cli import POLICY
    rules = tomllib.loads(POLICY.read_text())["rule"]
    assert any(r.get("decision") == "deny" and "push" in r.get("commandRegex", "") for r in rules)
    assert all(r["decision"] in ("allow", "deny") for r in rules)


def test_server_exposes_gemini_agent():
    from minions import server
    import asyncio
    names = [t.name for t in asyncio.run(server.mcp.list_tools())]
    assert "gemini_agent" in names


@pytest.mark.parametrize("path", [".gemini/settings.json", ".env"])
def test_repo_with_gemini_workspace_config_refused(repo, conf, monkeypatch, path):
    monkeypatch.setenv("FAKE_GEMINI_MODE", "ok")
    f = repo / path
    f.parent.mkdir(exist_ok=True)
    f.write_text("{}\n")
    git("add", "-A", "-f", cwd=repo)
    git("commit", "-qm", "add config", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    res = run_task("x", repo, conf=conf)
    assert res.status == "refused" and "workspace config" in res.message
