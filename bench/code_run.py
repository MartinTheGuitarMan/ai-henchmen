"""Coding bench: every text-writing roster model writes the tasks of bench/code_tasks.py, and the code is tested in a sandbox.

    uv run python bench/code_run.py --roster ROSTER.json --out bench/results/RUN --docker-host SSHHOST \
        [--env-file F ...] [--remote PORT=SSHHOST ...] [--models a,b] [--deadline-h 24] [--redo]
    uv run python bench/code_report.py bench/results/RUN > bench/results/RUN/RESULTS.md

Method: one shot, temperature 0, no examples, no retries. The prompt asks for a single fenced Python block; the block is
extracted here in code. Score is pass@1: hidden tests passed out of total, and fully solved tasks. Also recorded: latency
and the kind of every failure (no code block, truncated, syntax error, import error, timeout, killed, wrong answer).

Safety. Model code is untrusted and only ever runs in the Docker sandbox of bench/sandbox.py (no network, read-only root,
non-root, resource limits, 10 s). If Docker cannot be reached, or the sandbox self-test fails, this script stops before
calling any model and never runs the code anywhere else. Syntax is checked with `ast.parse`, which does not execute.

Quiet machines. Generation and execution are separate steps, so cloud models can generate at any time while code is only
run when the docker host is quiet.
- The docker host (the night host) is used only inside --night-windows (default 22:00-23:00 and 06:00-07:00, local time:
  the gaps between the Skylink night window and the Water Plant Co daytime window) and only while no Skylink or Water
  Plant Co job is found running there (pgrep over ssh); otherwise the run waits and tries again every 5 minutes.
  Models served from that host follow the same rule, plus the bench's memory/pressure/power gate.
- Models on this (day) machine use the gate of docs/dynamic-models.md: free memory, memory pressure, mains power, hold
  marker. The load-on-demand model is loaded by minions.manage (which refuses on battery) and unloaded again afterwards.
- Cloud models only ever see these invented public tasks (sensitive=false is fine) and wait out rate limits.
Results are written after every task, so a stopped run resumes; --deadline-h stops waiting and leaves a note instead.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import code_tasks  # noqa: E402
import run as modelfit  # noqa: E402  (bench/run.py: gate, rate-limit waiting, roster helpers)
import sandbox  # noqa: E402
from minions import backends, manage, reasoning  # noqa: E402
from minions.config import Roster  # noqa: E402
from minions.errors import Busy, LoadFailed, MinionError  # noqa: E402

SYSTEM = "You are a careful Python programmer. You follow the output format exactly."
MAX_TOKENS = 6000
MIN_TIMEOUT_S = 180
NIGHT_WINDOWS = "22:00-23:00,06:00-07:00"
JOB_PATTERN = "[n]ightly.sh|[a]gent_proposals.py|[a]gent_eval.py|[s]kylink-sim run|[w]pc-|[w]ater-plant"   # [x] keeps pgrep from matching itself
POLL_S = 300
DEAD = ("MINION_DOWN", "MINION_BACKEND_ERROR")
NIGHT_LOCK = threading.Lock()          # one thing at a time on the night host: a model call or a sandbox run
STATE = {"gen_done": False, "sandbox_ok": None}   # sandbox_ok: None = self-test not done yet
log = modelfit.log


# ---------------------------------------------------------------- extraction (pure)
FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[^\n]*\n(.*?)```", re.S)


def extract_code(raw: str, finish: str = "stop") -> dict:
    """{'code': str|None, 'failure': None|'no_code_block'|'truncated'|'syntax_error', 'blocks': n, 'detail': str}.
    Reasoning is stripped first. The first python (or untagged) fenced block is the answer; bare code without a fence is not
    accepted, because the prompt asked for a fence. An unclosed fence or an empty reply after a length stop is 'truncated'."""
    try:
        text = reasoning.strip_think(raw or "")
    except reasoning.Invalid:
        return {"code": None, "failure": "truncated", "blocks": 0, "detail": "ended inside an unterminated think block"}
    blocks = [(m[1].lower(), m[2]) for m in FENCE.finditer(text)]
    pick = next((b for b in blocks if b[0] in ("python", "py", "python3", "")), None)
    if pick is None:
        if finish == "length" or (text.count("```") % 2 == 1):
            return {"code": None, "failure": "truncated", "blocks": 0, "detail": "token budget ran out or fence never closed"}
        return {"code": None, "failure": "no_code_block", "blocks": len(blocks), "detail": text[:120]}
    code = pick[1]
    try:
        ast.parse(code)
    except (SyntaxError, ValueError) as e:
        return {"code": code, "failure": "syntax_error", "blocks": len(blocks), "detail": f"{e.__class__.__name__}: {e}"[:160]}
    return {"code": code, "failure": None, "blocks": len(blocks), "detail": ""}


def score(task: dict, ext: dict, run: dict | None) -> dict:
    """The task record for the report: passed/total, solved, and one failure kind (None when solved)."""
    total = task["n_tests"]
    if ext["failure"]:
        return {"passed": 0, "total": total, "solved": False, "failure": ext["failure"]}
    if run is None:
        return {"passed": 0, "total": total, "solved": False, "failure": "not_run"}
    passed = min(run["passed"], total)
    solved = run["kind"] == "ok" and passed == total
    return {"passed": passed, "total": total, "solved": solved, "failure": None if solved else run["kind"]}


# ---------------------------------------------------------------- gates
def in_windows(spec: str, now: datetime | None = None) -> bool:
    from minions import lifecycle
    now = now or datetime.now()
    return any(lifecycle.in_window(w, now) for w in re.split(r"[,\s]+", spec) if w)


def jobs_running(host: str) -> list[str] | None:
    """Lines of Skylink / Water Plant Co processes on the host. None when the host cannot be asked: treat as busy."""
    try:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, f"pgrep -fl '{JOB_PATTERN}' | cut -c1-80; true"],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.split("\n")[:-1] if r.returncode == 0 else None


def night_quiet(host: str, windows: str) -> tuple[bool, str]:
    if not host:      # docker on this machine: nothing of Skylink's or Water Plant Co's to disturb
        return True, ""
    if not in_windows(windows):
        return False, f"outside the night host's allowed windows ({windows})"
    jobs = jobs_running(host)
    if jobs is None:
        return False, "could not ask the night host whether jobs are running"
    if any(j.strip() for j in jobs):
        return False, "a Skylink or Water Plant Co job is running: " + jobs[0].strip()
    return True, ""


def wait_until(ok_fn, what: str, deadline: float) -> bool:
    """Poll ok_fn() -> (ok, reason) every POLL_S until true or the deadline. Returns False at the deadline."""
    said = None
    while True:
        ok, why = ok_fn()
        if ok:
            return True
        if time.time() >= deadline:
            return False
        if why != said:
            log(f"{what}: waiting ({why})")
            said = why
        time.sleep(min(POLL_S, max(1, deadline - time.time())))


# ---------------------------------------------------------------- generation
def prompt_for(task: dict) -> list:
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task["prompt"]}]


def generate_one(cfg, task: dict, max_tokens: int = MAX_TOKENS) -> dict:
    res, lat, e = modelfit.attempt(lambda: backends.complete_ex(cfg, prompt_for(task), None, max_tokens=max_tokens))
    if e:
        return {"error": e.code, "detail": str(e)[:200], "latency": round(lat, 2)}
    raw, finish = res
    return {"raw": raw, "finish": finish, "latency": round(lat, 2), **{k: v for k, v in extract_code(raw, finish).items()}}


def gen_path(out: Path, name: str) -> Path:
    return out / "gen" / f"{name}.json"


def load_doc(path: Path, cfg, machine: str, redo: bool) -> dict:
    if path.exists() and not redo:
        return json.loads(path.read_text())
    return {"model": cfg.name, "backend_model": cfg.model, "cloud": cfg.cloud, "machine": machine, "tasks": {}}


def prepare_local(cfg, machine: str, env: dict, deadline: float):
    """Wait for the quiet gate and load the model if minions manages it. Returns (cleanup, None) or (None, skip reason)."""
    if cfg.backend == "lmstudio" and cfg.manage:
        roster = modelfit.single_roster(replace(cfg, context=8192))
        state = {"why": ""}

        def try_load():
            try:
                manage.load(roster, cfg.name, env=env)
                return True, ""
            except (Busy, LoadFailed) as e:
                state["why"] = str(e)
                return False, str(e)
        if not wait_until(try_load, f"{cfg.name} load", deadline):
            return None, state["why"]
        return (lambda: manage.unload(roster, cfg.name, env=env)), None
    size = modelfit.model_size_gb(cfg)
    before = modelfit.resident(cfg)
    reasons: list = []

    def gate_ok():
        g = modelfit.gate(machine, size)
        reasons[:] = g["reasons"]
        return g["allowed"], "; ".join(g["reasons"])
    if not wait_until(gate_ok, cfg.name, deadline):
        return None, "; ".join(reasons)
    root = modelfit.ollama_root(cfg)
    if cfg.model in before or not root:
        return (lambda: None), None
    return (lambda: modelfit.http_json(f"{root}/api/generate", {"model": cfg.model, "keep_alive": 0})), None


def work_group(cfgs: list, machine: str, out: Path, tasks: list, args, deadline: float) -> None:
    is_night = machine == args.night_ssh
    env = {k: v for k, v in os.environ.items() if k != "MINION_QUIET_WINDOWS"}
    for cfg in cfgs:
        cfg = replace(cfg, timeout=max(cfg.timeout, MIN_TIMEOUT_S))
        path = gen_path(out, cfg.name)
        doc = load_doc(path, cfg, "cloud" if cfg.cloud else "night-host" if is_night else "day-host", args.redo)
        todo = [t for t in tasks if t["id"] not in doc["tasks"] or doc["tasks"][t["id"]].get("error") in DEAD]
        if not todo:
            continue
        cleanup = None
        if is_night:
            while STATE["sandbox_ok"] is None and time.time() < deadline:
                time.sleep(15)
            if not STATE["sandbox_ok"]:
                doc["skipped"] = "sandbox not usable (self-test not passed), so no code could be run"
                modelfit.save(path, doc)
                continue
        if not cfg.cloud:
            cleanup, skip = prepare_local(cfg, machine, env, deadline)
            if cleanup is None:
                doc["skipped"] = skip or "gate never opened"
                modelfit.save(path, doc)
                log(f"{cfg.name}: skipped ({doc['skipped']})")
                continue
            doc.pop("skipped", None)
        dead_run = 0
        for t in todo:
            if is_night and not wait_until(lambda: night_quiet(machine, args.night_windows), f"{cfg.name}/{t['id']}", deadline):
                doc["note"] = "stopped at the deadline: the night host was not quiet"
                break
            if not cfg.cloud and not is_night:
                while modelfit.busy_now(machine) and time.time() < deadline:
                    log(f"{cfg.name}: machine busy, pausing")
                    time.sleep(POLL_S)
            if is_night:
                with NIGHT_LOCK:
                    rec = generate_one(cfg, t, args.max_tokens)
            else:
                rec = generate_one(cfg, t, args.max_tokens)
            doc["tasks"][t["id"]] = rec
            modelfit.save(path, doc)
            log(f"{cfg.name}/{t['id']}: {rec.get('error') or rec.get('failure') or 'code'} {rec['latency']}s")
            dead_run = dead_run + 1 if rec.get("error") in DEAD else 0
            if dead_run >= 3 and all(r.get("error") in DEAD for r in doc["tasks"].values()):
                doc["unavailable"] = rec.get("detail")
                break
        modelfit.save(path, doc)
        if cleanup:
            try:
                cleanup()
            except MinionError as e:
                log(f"{cfg.name}: unload failed ({e})")
            log(f"{cfg.name}: unloaded")


# ---------------------------------------------------------------- execution
def execute_loop(sb: sandbox.Sandbox, out: Path, tasks: list, args, deadline: float) -> None:
    by_id = {t["id"]: t for t in tasks}
    (out / "exec").mkdir(exist_ok=True)
    if not wait_until(lambda: night_quiet(args.docker_host, args.night_windows), "sandbox self-test", deadline):
        STATE["sandbox_ok"] = False
        log("sandbox self-test never got a quiet night host before the deadline: nothing was run")
        return
    try:
        st_path = out / "selftest.json"
        st = json.loads(st_path.read_text()) if st_path.exists() else None
        if st is None:
            with NIGHT_LOCK:
                st = sandbox.selftest(sb)
            modelfit.save(st_path, st)
            log(f"sandbox self-test: {st}")
        if st["ok"]:
            sb.stage({t["id"]: t["tests"] for t in tasks})
    except sandbox.SandboxUnavailable as e:
        log(f"STOP: sandbox unavailable ({e}); nothing will be run")
        STATE["sandbox_ok"] = False
        return
    STATE["sandbox_ok"] = bool(st["ok"])
    if not st["ok"]:
        log("STOP: the sandbox self-test failed; no model output will be run. See selftest.json")
        return
    while True:
        pending = []
        for gp in sorted((out / "gen").glob("*.json")):
            gdoc = json.loads(gp.read_text())
            ep = out / "exec" / gp.name
            edoc = json.loads(ep.read_text()) if ep.exists() else {"model": gdoc["model"], "tasks": {}}
            for tid, rec in gdoc["tasks"].items():
                if tid in by_id and tid not in edoc["tasks"] and rec.get("code") and not rec.get("failure"):
                    pending.append((gp, ep, edoc, tid, rec))
        if not pending:
            if STATE["gen_done"] or time.time() >= deadline:
                return
            time.sleep(30)
            continue
        if not wait_until(lambda: night_quiet(args.docker_host, args.night_windows), "sandbox", deadline):
            log("sandbox: deadline reached with runs still waiting")
            return
        for gp, ep, edoc, tid, rec in pending:
            ok, why = night_quiet(args.docker_host, args.night_windows)
            if not ok:
                break
            with NIGHT_LOCK:
                res = sb.run(tid, rec["code"])
            if res["kind"] == "sandbox_error":
                log(f"sandbox error for {edoc['model']}/{tid}: {res.get('stderr') or res.get('tail')}; will retry later")
                continue
            edoc["tasks"][tid] = res
            modelfit.save(ep, edoc)
            log(f"exec {edoc['model']}/{tid}: {res['kind']} {res['passed']}/{by_id[tid]['n_tests']} {res['elapsed']}s")


# ---------------------------------------------------------------- main
def text_models(roster: Roster) -> tuple[list, list]:
    """Every roster model that writes text: decision models (systemone) are left out, and so is a second entry for a model
    that is already listed (the same backend, address and model name, for example a judge entry). Returns (models, notes)."""
    seen, out, notes = {}, [], []
    for n, m in roster.models.items():
        if m.backend == "systemone" or m.kind == "decision":
            notes.append(f"{n}: decision model, does not write code")
            continue
        key = (m.backend, m.base_url, m.model)
        if key in seen:
            notes.append(f"{n}: same model as {seen[key]}, not run twice")
            continue
        seen[key] = n
        out.append(m)
    return out, notes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roster", default=os.environ.get("MINION_ROSTER"))
    ap.add_argument("--env-file", action="append", default=[])
    ap.add_argument("--models")
    ap.add_argument("--tasks", help="comma-separated task ids (default: all)")
    ap.add_argument("--remote", action="append", default=[], metavar="PORT=SSHHOST",
                    help="a local model on this port runs on another machine (the night host); gate it there over ssh")
    ap.add_argument("--docker-host", default=os.environ.get("CODEBENCH_DOCKER_HOST"), help="ssh name of the docker host (default: local docker)")
    ap.add_argument("--night-windows", default=NIGHT_WINDOWS)
    ap.add_argument("--deadline-h", type=float, default=24.0)
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    ap.add_argument("--redo", action="store_true", help="generate again")
    ap.add_argument("--redo-exec", action="store_true", help="run the sandbox again on stored code")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if not args.roster:
        sys.exit("--roster or MINION_ROSTER is required")
    out = Path(args.out)
    (out / "gen").mkdir(parents=True, exist_ok=True)
    modelfit.LOG_FILE = out / "run.log"
    modelfit.load_env_files(args.env_file)
    deadline = time.time() + args.deadline_h * 3600

    tasks = [t for t in code_tasks.TASKS if not args.tasks or t["id"] in args.tasks.split(",")]
    # 1. Docker must answer before any model is called. The self-test and the copy of the test files wait for a quiet
    #    night host and run first in the execution thread; until they pass nothing is run, and models on the night host wait.
    sb = sandbox.Sandbox(args.docker_host)
    try:
        sb.check()
    except sandbox.SandboxUnavailable as e:
        sys.exit(f"STOP: no usable Docker sandbox ({e}). Nothing was run and no model was called.")
    if args.redo_exec:
        for f in (out / "exec").glob("*.json"):
            f.unlink()
        (out / "selftest.json").unlink(missing_ok=True)

    raw = json.loads(Path(args.roster).expanduser().read_text())
    roster = Roster.from_dict({"models": raw["models"]})
    models, notes = text_models(roster)
    if args.models:
        models = [m for m in models if m.name in args.models.split(",")]
    (out / "notes.json").write_text(json.dumps({"notes": notes, "models": [m.name for m in models]}, indent=1))
    remote = {int(p): h for p, h in (x.split("=") for x in args.remote)}
    groups = defaultdict(list)
    for cfg in models:
        port = urlparse(cfg.base_url).port
        groups[("cloud", urlparse(cfg.base_url).hostname) if cfg.cloud else (remote.get(port, "local"), "")].append(cfg)
    args.night_ssh = args.docker_host or ""
    log(f"models: {[m.name for m in models]}; tasks: {len(tasks)}; groups: {['cloud' if k[0] == 'cloud' else 'night-host' if k[0] == args.night_ssh else 'day-host' for k in groups]}")
    with ThreadPoolExecutor(len(groups) + 1) as ex:
        ex_f = ex.submit(execute_loop, sb, out, tasks, args, deadline)
        futs = [ex.submit(work_group, cfgs, "local" if k[0] == "cloud" else k[0], out, tasks, args, deadline)
                for k, cfgs in groups.items()]
        for f in futs:
            f.result()
        STATE["gen_done"] = True
        ex_f.result()
    log("done")


if __name__ == "__main__":
    main()
