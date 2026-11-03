"""Gemini CLI as an agent, run headless in a throwaway clone.

Pattern adapted from clink in PAL MCP Server (BeehiveInnovations, Apache-2.0; see NOTICE): subprocess with
`-o json`, JSON error recovery, roles as prompt files, and the <SUMMARY> cap on long output. Changed here: no
--yolo, sandbox on, a policy file that allows only tests and read-only git, a clone with no remote, the privacy
map as gate, and pushed commits only. The result is a proposal (a patch), never a change.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from minions import privacy

from . import config as cfg
from .isolation import IsolationError, collect_diff, is_pushed, make_clone, repo_root, resolve_commit

HERE = Path(__file__).resolve().parent
POLICY = HERE / "policies" / "gemini-agent.toml"
SUMMARY_RE = re.compile(r"<SUMMARY>(.*?)</SUMMARY>", re.IGNORECASE | re.DOTALL)
EXIT_TURN_LIMIT = 53
STATUSES = ("ok", "refused", "cli_error", "timeout", "rate_limited", "busy", "turn_limit")
BUSY = re.compile(r"\b503\b|UNAVAILABLE|high demand|overloaded", re.IGNORECASE)


@dataclass
class RunResult:
    status: str
    run_id: str
    message: str
    summary: str | None = None
    response: str | None = None
    patch_path: str | None = None
    diff_stat: str | None = None
    agent_commits: list[str] = field(default_factory=list)
    clone_path: str | None = None
    base_commit: str | None = None
    tests: dict[str, Any] | None = None
    stats: dict[str, Any] | None = None
    duration_s: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, [], {})}


def build_command(settings: cfg.GeminiSettings, role: str) -> list[str]:
    exe = shutil.which(settings.command)
    if exe is None:
        raise FileNotFoundError(f"{settings.command!r} not found on PATH")
    # --skip-trust: headless runs refuse untrusted folders, and the clone is new every run. Trusting it would let a
    # repo's own .gemini/ settings, .env files and MCP servers load, so _workspace_config refuses clones that have any.
    cmd = [exe, "-o", "json", "--skip-trust", "--approval-mode", cfg.ROLE_APPROVAL[role], "--policy", str(POLICY)]
    if settings.sandbox:
        cmd.append("--sandbox")
    if settings.model:
        cmd += ["-m", settings.model]
    return cmd


def _run(cmd: list[str], cwd: Path, stdin: str, timeout: int) -> tuple[int | None, str, str]:
    """Run in its own process group so a timeout kills the whole tree."""
    proc = subprocess.Popen(
        cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    try:
        out, err = proc.communicate(stdin, timeout=timeout)
        return proc.returncode, out, err
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
        return None, out, err


def parse_output(stdout: str, stderr: str) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    """Return (response text, stats, error block) from `gemini -o json` output."""
    payload: Any = None
    try:
        payload = json.loads(stdout) if stdout.strip() else None
    except json.JSONDecodeError:
        payload = None
    if not isinstance(payload, dict):
        # Errors sometimes arrive as JSON after a text prologue, on either stream.
        combined = "\n".join(p for p in (stderr, stdout) if p)
        brace = combined.find("{")
        if brace != -1:
            try:
                payload = json.loads(combined[brace:])
            except json.JSONDecodeError:
                payload = None
    if not isinstance(payload, dict):
        return "", {}, None
    response = payload.get("response")
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    error = payload.get("error") if isinstance(payload.get("error"), dict) else None
    return (response.strip() if isinstance(response, str) else ""), stats, error


def cap_response(text: str, limit: int) -> tuple[str, str | None]:
    """Return (response within limit, summary if any)."""
    match = SUMMARY_RE.search(text)
    summary = match.group(1).strip() if match else None
    if len(text) <= limit:
        return text, summary
    if summary:
        return summary[:limit], summary[:limit]
    excerpt = text[: min(4000, limit // 2)]
    return f"[output was {len(text)} chars, over the {limit} limit; first {len(excerpt)} shown]\n{excerpt}", None


def _classify(code: int | None, stderr: str, error: dict | None, response: str, timeout: int) -> tuple[str, str]:
    if code is None:
        return "timeout", f"killed after {timeout} s"
    if "429" in stderr or "rate limit" in stderr.lower() or (error and str(error.get("code")) == "429"):
        return "rate_limited", "Gemini reported a rate limit (429); the free quota may be spent for now"
    if BUSY.search(stderr) or (error and str(error.get("code")) == "503"):
        return "busy", "Gemini reported the model overloaded (503); try again later or pick another model"
    if code == EXIT_TURN_LIMIT:
        return "turn_limit", "Gemini CLI hit its turn limit"
    if code != 0 or error:
        detail = (error or {}).get("message") or stderr.strip()[-500:] or f"exit code {code}"
        return "cli_error", f"Gemini CLI failed: {detail}"
    if not response:
        return "cli_error", "Gemini CLI returned no text"
    return "ok", "done; the patch is a proposal, nothing was applied"


def _workspace_config(clone: Path) -> list[str]:
    """Files in the clone that Gemini CLI would load from a trusted workspace (settings, MCP servers, env, memory)."""
    found = [p.name for p in clone.glob(".env*") if p.is_file()]
    if (clone / ".gemini").exists():
        found.append(".gemini/")
    return sorted(found)


def _gate(root: Path, base: str, conf: cfg.AgentConfig) -> str | None:
    """Reason to refuse, or None. Cloud agent: the repo must be public in the privacy map, and the base commit
    already pushed (unpushed work is not yet public) unless the repo is listed as unpushed_ok."""
    cls = privacy.class_of(str(root))
    if cls["class"] != "low":
        return (f"privacy map gives {root} class {cls['class']!r} (map: {cls['map']}); a cloud agent needs 'low'. "
                f"Label the repo low in the privacy map if it is public.")
    if not conf.unpushed_ok(root) and not is_pushed(root, base):
        return (f"base commit {base[:12]} is not on any remote-tracking branch: unpushed work is not yet public. "
                f"Push first, pick a pushed base_ref, or list the repo in unpushed_ok_repos.")
    return None


def run_task(
    task: str,
    repo: str | Path,
    role: str = "default",
    base_ref: str = "HEAD",
    test_command: str | None = None,
    conf: cfg.AgentConfig | None = None,
) -> RunResult:
    conf = conf or cfg.load()
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]

    def refuse(msg: str) -> RunResult:
        return RunResult("refused", run_id, msg)

    if role not in cfg.ROLE_APPROVAL:
        return refuse(f"unknown role {role!r}; use one of {sorted(cfg.ROLE_APPROVAL)}")
    if not isinstance(task, str) or not task.strip():
        return refuse("task must be a non-empty string")
    try:
        root = repo_root(Path(repo).expanduser())
        base = resolve_commit(root, base_ref)
    except IsolationError as exc:
        return refuse(str(exc))
    reason = _gate(root, base, conf)
    if reason:
        return refuse(reason)
    try:
        cmd = build_command(conf.gemini, role)
    except FileNotFoundError as exc:
        return refuse(str(exc))

    run_dir = conf.runs_dir / run_id
    clone = run_dir / "work"
    try:
        make_clone(root, clone, base, f"agent/gemini/{run_id}")
    except IsolationError as exc:
        return refuse(str(exc))

    found = _workspace_config(clone)
    if found:
        return refuse(f"the repo has Gemini CLI workspace config ({', '.join(found)}), which a trusted run would load; "
                      f"remove it from the repo or run the agent elsewhere")

    prompt = f"{(HERE / 'prompts' / f'{role}.txt').read_text(encoding='utf-8')}\n\n=== TASK ===\n{task.strip()}\n"
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

    start = time.monotonic()
    code, stdout, stderr = _run(cmd, clone, prompt, conf.gemini.timeout_s)
    duration = round(time.monotonic() - start, 1)
    (run_dir / "stdout.json").write_text(stdout, encoding="utf-8")
    (run_dir / "stderr.txt").write_text(stderr, encoding="utf-8")

    response, stats, error = parse_output(stdout, stderr)
    response, summary = cap_response(response, conf.gemini.max_response_chars)
    status, message = _classify(code, stderr, error, response, conf.gemini.timeout_s)

    patch, stat, commits = collect_diff(clone, base)
    patch_path = None
    if patch.strip():
        patch_file = run_dir / "changes.patch"
        patch_file.write_text(patch, encoding="utf-8")
        patch_path = str(patch_file)

    tests = None
    if test_command and status in ("ok", "turn_limit"):
        t_code, t_out, t_err = _run(shlex.split(test_command), clone, "", conf.gemini.timeout_s)
        tests = {"command": test_command, "exit_code": t_code, "passed": t_code == 0,
                 "output_tail": (t_out + t_err)[-3000:]}

    result = RunResult(
        status=status, run_id=run_id, message=message, summary=summary, response=response,
        patch_path=patch_path, diff_stat=stat.strip() or None, agent_commits=commits,
        clone_path=str(clone), base_commit=base, tests=tests, stats=stats or None, duration_s=duration,
    )
    (run_dir / "result.json").write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return result
