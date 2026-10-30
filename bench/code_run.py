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
import contextlib
import fcntl
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
NIGHT_FLOCK = "/tmp/codebench-night-host.lock"     # across processes: a model on the night host and a sandbox run never overlap
NIGHT_FLOOR_PCT = 10        # free memory that must remain after loading, on the night host inside its windows (25 elsewhere)
DEFAULT_FLOOR_PCT = 25
SESSION_MIN = 20            # one model session on the night host is at most this long, so sandbox runs get turns between sessions
UNLOAD_GUARD_MIN = 8        # no new night-host model call in the last minutes of a window, so the model is unloaded in time
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


def minutes_left(spec: str, now: datetime | None = None) -> float:
    """Minutes until the end of the window (of HH:MM-HH:MM windows that do not cross midnight) that contains now; 0 if none."""
    now = now or datetime.now()
    cur = now.hour * 60 + now.minute + now.second / 60
    for w in re.split(r"[,\s]+", spec):
        m = re.fullmatch(r"(\d\d):(\d\d)-(\d\d):(\d\d)", w or "")
        if m:
            a, b = int(m[1]) * 60 + int(m[2]), int(m[3]) * 60 + int(m[4])
            if a <= cur < b:
                return b - cur
    return 0.0


def night_model_ok(host: str, windows: str) -> tuple[bool, str]:
    """May a model on the night host be loaded or called now? Quiet, and not in the last minutes of the window."""
    ok, why = night_quiet(host, windows)
    if ok and host and minutes_left(windows) < UNLOAD_GUARD_MIN:
        return False, "too close to the end of the window to start a model call"
    return ok, why


def floor_pct_now(machine_is_night: bool, windows: str) -> int:
    """The memory margin after loading: 10 percent on the night host inside its windows, 25 otherwise."""
    return NIGHT_FLOOR_PCT if machine_is_night and in_windows(windows) else DEFAULT_FLOOR_PCT


class NightExclusive:
    """Cross-process exclusion on the night host: held for a whole model session (load to unload) or one sandbox run."""

    def __init__(self, path: str = NIGHT_FLOCK):
        self.path, self.fd = path, None

    def acquire(self, timeout: float) -> bool:
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        end = time.time() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.fd = fd
                return True
            except OSError:
                if time.time() >= end:
                    os.close(fd)
                    return False
                time.sleep(2)

    def release(self) -> None:
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None


@contextlib.contextmanager
def sandbox_slot(host: str, timeout: float = 600.0):
    """Yields True once no night-host model is loaded by any bench process (and holds that for the body), else False."""
    if not host:
        yield True
        return
    lock = NightExclusive()
    got = lock.acquire(timeout)
    try:
        yield got
    finally:
        if got:
            lock.release()


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


def prepare_local(cfg, machine: str, env: dict, deadline: float, floor_fn=lambda: DEFAULT_FLOOR_PCT):
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
        g = modelfit.gate(machine, size, floor_fn())
        reasons[:] = g["reasons"]
        return g["allowed"], "; ".join(g["reasons"])
    if not wait_until(gate_ok, cfg.name, deadline):
        return None, "; ".join(reasons)
    root = modelfit.ollama_root(cfg)
    if cfg.model in before or not root:
        return (lambda: None), None
    return (lambda: modelfit.http_json(f"{root}/api/generate", {"model": cfg.model, "keep_alive": 0})), None


def work_model(cfg, machine: str, out: Path, tasks: list, args, deadline: float) -> str:
    """Generate what is still missing for one model. Returns 'done', or 'deferred' when the gate, the night window or the
    sandbox self-test did not allow it yet (nothing stays loaded then). A deferred model is tried again later."""
    is_night = machine == args.night_ssh
    env = {k: v for k, v in os.environ.items() if k != "MINION_QUIET_WINDOWS"}
    cfg = replace(cfg, timeout=max(cfg.timeout, args.min_timeout))
    path = gen_path(out, cfg.name)
    doc = load_doc(path, cfg, "cloud" if cfg.cloud else "night-host" if is_night else "day-host", args.redo)
    todo = [t for t in tasks if t["id"] not in doc["tasks"] or doc["tasks"][t["id"]].get("error") in DEAD]
    if args.only is not None:
        todo = [t for t in todo if t["id"] in args.only.get(cfg.name, ())]
    if not todo or doc.get("unavailable"):
        return "done"
    if is_night:
        if STATE["sandbox_ok"] is None:
            return "deferred"
        if not STATE["sandbox_ok"]:
            doc["skipped"] = "sandbox not usable (self-test not passed), so no code could be run"
            modelfit.save(path, doc)
            return "done"
        if not night_model_ok(machine, args.night_windows)[0]:
            return "deferred"          # never load a model on the night host outside its window
    lock = NightExclusive() if is_night and not cfg.cloud else None
    if lock and not lock.acquire(120):
        return "deferred"              # a sandbox run is in progress: a model and a sandbox run never overlap on the night host
    cleanup = None
    try:
        return _work_model(cfg, machine, args, deadline, path, doc, todo, env, is_night)
    finally:
        if lock:
            lock.release()


def _work_model(cfg, machine, args, deadline, path, doc, todo, env, is_night) -> str:
    cleanup = None
    if not cfg.cloud:
        cleanup, skip = prepare_local(cfg, machine, env, min(deadline, time.time() + 120),
                                      lambda: floor_pct_now(is_night, args.night_windows))
        if cleanup is None:
            log(f"{cfg.name}: deferred ({skip or 'gate never opened'})")
            return "deferred"
        doc.pop("skipped", None)
    dead_run, result = 0, "done"
    session_end = time.time() + SESSION_MIN * 60
    for t in todo:
        if is_night and (not night_model_ok(machine, args.night_windows)[0] or time.time() > session_end):
            result = "deferred"        # window closing, a job started, or this session's slice is used up: unload, come back later
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
    return result


def work_group(cfgs: list, machine: str, out: Path, tasks: list, args, deadline: float) -> None:
    """One machine's models, one after another. A model that cannot start now (memory gate, night window) does not block
    the others: it waits in the queue and is tried again every few minutes until the deadline, then recorded as not run."""
    pending = list(cfgs)
    while pending and time.time() < deadline:
        for cfg in list(pending):
            if work_model(cfg, machine, out, tasks, args, deadline) == "done":
                pending.remove(cfg)
        if pending:
            time.sleep(min(POLL_S, max(1, deadline - time.time())))
    for cfg in pending:
        path = gen_path(out, cfg.name)
        doc = load_doc(path, cfg, "night-host" if machine == args.night_ssh else "day-host", False)
        doc["skipped"] = "gate or night window never allowed it before the deadline"
        modelfit.save(path, doc)
        log(f"{cfg.name}: not run ({doc['skipped']})")


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
            with NIGHT_LOCK, sandbox_slot(args.docker_host, 1800) as got:
                if not got:
                    raise sandbox.SandboxUnavailable("night host busy with a model for too long")
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
            with NIGHT_LOCK, sandbox_slot(args.docker_host) as got:
                if not got or not night_quiet(args.docker_host, args.night_windows)[0]:
                    break
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
    ap.add_argument("--min-timeout", type=int, default=MIN_TIMEOUT_S, help="per-call timeout floor, seconds")
    ap.add_argument("--only-truncated-of", metavar="RUNDIR",
                    help="second protocol: only the (model, task) pairs that ended 'truncated' in RUNDIR (use with a larger --max-tokens and a new --out)")
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

    args.only = None
    if args.only_truncated_of:
        args.only = {}
        for gp in sorted((Path(args.only_truncated_of) / "gen").glob("*.json")):
            g = json.loads(gp.read_text())
            ids = {tid for tid, r in g["tasks"].items() if r.get("failure") == "truncated"}
            if ids:
                args.only[g["model"]] = ids
        log(f"second protocol: max_tokens {args.max_tokens}, pairs {sum(map(len, args.only.values()))}: {sorted(args.only)}")
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
