"""Coding bench for an agent: Gemini CLI (gemini_agent) on the 25 tasks of bench/code_tasks.py.

    uv run python bench/agent_run.py --out bench/results/RUN [--tasks a,b] [--model NAME] [--redo]
    uv run python bench/code_run.py --roster ROSTER.json --models none --out bench/results/RUN --docker-host SSHHOST
    uv run python bench/code_report.py bench/results/RUN > bench/results/RUN/RESULTS.md

Step 1 (this script) only generates. For every task it builds a tiny git repo in a temporary folder (TASK.md with the
task text, solution.py empty or holding the buggy code), runs the agent on it through agents.gemini_cli.run_task, and
reads back the solution.py the agent left in its clone. The agent may read, edit and run its own pytest inside Gemini
CLI's sandbox, as it would in real use; it never sees the hidden tests.

Step 2 is the existing bench: the result is stored in the same gen/<model>.json format as code_run.py writes (the
solution wrapped in one fenced block), so `code_run.py --models none` runs it against the hidden tests in the Docker
sandbox (no network, read-only, limits) and code_report.py scores it next to the one-shot models. The hidden tests and
the agent's code never run on this machine outside that sandbox.

Also recorded per task: the agent's status (ok, refused, cli_error, timeout, rate_limited, turn_limit), wall time,
token stats, which files the patch touched, and whether it touched anything but solution.py and test files of its own.

The temporary repos hold only the invented public task text, so this script labels them `low` in a private
privacy map of its own and lists them as unpushed_ok. It never changes the real privacy map or agents config.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import code_run  # noqa: E402  (extract_code, gen_path)
import code_tasks  # noqa: E402

from agents import config as acfg  # noqa: E402
from agents.gemini_cli import run_task  # noqa: E402

MODEL_NAME = "gemini-cli-agent"
OWN_FILES = re.compile(r"^(solution\.py|(tests?/)?test_[\w-]*\.py|(tests?/)?conftest\.py)$")   # TASK.md is not one
AGENT_NOTE = ("Write the complete module in solution.py in this folder (replace what is there). Standard library only. "
              "You may add your own test file and run pytest to check your work. Do not change TASK.md.")


def task_text(task: dict) -> str:
    body = task["prompt"]
    if body.endswith(code_tasks.FENCE_RULE):
        body = body[: -len(code_tasks.FENCE_RULE)].rstrip()
    return body + "\n\n" + AGENT_NOTE + "\n"


def git(*args: str, cwd: Path) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout


def make_task_repo(root: Path, task: dict) -> Path:
    repo = root / task["id"]
    repo.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=repo)
    git("config", "user.name", "bench", cwd=repo)
    git("config", "user.email", "bench@localhost", cwd=repo)
    (repo / "TASK.md").write_text(task_text(task), encoding="utf-8")
    (repo / "solution.py").write_text(task.get("buggy") or "", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-qm", "task", cwd=repo)
    return repo


def touched(patch: str) -> list[str]:
    return sorted(set(re.findall(r"^diff --git a/(\S+) b/", patch, re.M)))


def record(task: dict, res, elapsed: float) -> dict:
    rec: dict = {"agent_status": res.status, "latency": round(elapsed, 2), "message": res.message[:300]}
    if res.stats:
        rec["stats"] = res.stats
    patch = Path(res.patch_path).read_text(encoding="utf-8") if res.patch_path else ""
    rec["files"] = touched(patch)
    rec["outside_own_files"] = [f for f in rec["files"] if not OWN_FILES.match(f)]
    sol = Path(res.clone_path) / "solution.py" if res.clone_path else None
    if res.status not in ("ok", "turn_limit") or sol is None or not sol.exists():
        rec.update({"error": f"AGENT_{res.status.upper()}", "detail": res.message[:200]})
        return rec
    code = sol.read_text(encoding="utf-8")
    raw = f"```python\n{code}```" if code.endswith("\n") else f"```python\n{code}\n```"
    rec.update({"raw": raw, "finish": "stop", **code_run.extract_code(raw, "stop")})
    if task.get("buggy") and code == task["buggy"]:
        rec["note"] = "solution.py unchanged"
    return rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tasks", help="comma-separated task ids (default: all 25)")
    ap.add_argument("--model", help="Gemini model name (default: the CLI's own)")
    ap.add_argument("--timeout", type=int, default=900, help="per task, seconds")
    ap.add_argument("--pause", type=float, default=5.0, help="seconds between tasks (free-tier rate limits)")
    ap.add_argument("--redo", action="store_true")
    args = ap.parse_args(argv)

    out = Path(args.out)
    path = code_run.gen_path(out, MODEL_NAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = json.loads(path.read_text()) if path.exists() and not args.redo else {
        "model": MODEL_NAME, "backend_model": args.model or "gemini-cli-default", "cloud": True,
        "machine": "day-host", "kind": "agent", "tasks": {}}
    tasks = [t for t in code_tasks.TASKS if not args.tasks or t["id"] in args.tasks.split(",")]

    base = acfg.load()
    with tempfile.TemporaryDirectory(prefix="agent-bench-") as tmp:
        root = Path(tmp).resolve()
        pmap = root / "privacy-map.json"
        pmap.write_text(json.dumps({"version": 1, "default": "personal", "paths": [{"path": str(root), "class": "low"}]}))
        os.environ["MINION_PRIVACY_MAP"] = str(pmap)
        gem = acfg.GeminiSettings(command=base.gemini.command, model=args.model or base.gemini.model,
                                  timeout_s=args.timeout, sandbox=True, max_response_chars=base.gemini.max_response_chars)
        for t in tasks:
            if t["id"] in doc["tasks"]:
                continue
            repo = make_task_repo(root / "repos", t)
            conf = acfg.AgentConfig(gemini=gem, runs_dir=root / "runs", unpushed_ok_repos=[repo.resolve()])
            start = time.monotonic()
            res = run_task(f"Do the task described in TASK.md.", repo, conf=conf)
            rec = record(t, res, time.monotonic() - start)
            doc["tasks"][t["id"]] = rec
            path.write_text(json.dumps(doc, indent=1))
            print(f"{t['id']}: {rec['agent_status']} {rec.get('failure') or rec.get('error') or 'code'} "
                  f"{rec['latency']}s files={rec['files']}", flush=True)
            if rec["agent_status"] in ("rate_limited", "busy"):
                del doc["tasks"][t["id"]]          # not a result: this task is tried again on the next run
                path.write_text(json.dumps(doc, indent=1))
                print(f"{rec['agent_status']}: stopping; rerun later to resume", flush=True)
                break
            time.sleep(args.pause)
    return 0


if __name__ == "__main__":
    sys.exit(main())
