"""Retry-loop eval for `write_code`: a function from a spec, accepted only if its tests pass in the sandbox.

    uv run python bench/code_loop.py --roster ROSTER.json --run bench/results/RUN --docker-host SSHHOST [--env-file F ...]
        [--remote PORT=SSHHOST ...] [--models a,b] [--deadline-h 24]
    uv run python bench/code_loop_report.py bench/results/RUN > bench/results/RUN/LOOP.md

This is an eval, not a server tool. Attempt 1 is the stored one-shot answer of bench/code_run.py (same prompt,
temperature 0). Each task's hidden tests are dealt out alternately into visible and held-out files
(code_tasks.split_tests). The answer is run against the visible tests; if they all pass it is accepted. Otherwise the model
sees its own answer and the pytest failures of the visible tests (never a held-out test) and answers again, at most 3
attempts in all. The final code (first accepted, else last) is scored on all hidden tests and on the held-out tests alone.
The pass criteria were written first, in HYPOTHESIS-write-code.md.

Same safety and same quiet-machine rules as code_run.py: model code runs only in the Docker sandbox, on the night host
only inside its windows while no Skylink or Water Plant Co job runs; a model on the night host is loaded only inside the
window and unloaded when it closes; models that cannot start now wait in a queue; a model whose one-shot results are not
complete is "not run" (never a fail).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import code_run as cr  # noqa: E402
import code_tasks  # noqa: E402
import run as modelfit  # noqa: E402
import sandbox  # noqa: E402
from minions import backends  # noqa: E402
from minions.config import Roster  # noqa: E402
from minions.errors import MinionError  # noqa: E402

MAX_ATTEMPTS = 3
FEEDBACK_CHARS = 2500
log = modelfit.log


# ---------------------------------------------------------------- pure parts
def failure_text(ext: dict, res: dict | None) -> str:
    """What the model is told about a failed attempt: the extraction problem, or the visible tests' pytest output."""
    if ext.get("failure") and not ext.get("code"):
        return (f"Your reply had no usable Python code block ({ext['failure']}: {ext.get('detail', '')[:120]}). "
                "Answer with the complete solution in one fenced python block.")
    if ext.get("failure") == "syntax_error":
        return f"Your code has a syntax error: {ext.get('detail', '')[:200]}"
    if res is None:
        return "The tests could not be run."
    if res["kind"] == "timeout":
        return "The tests did not finish within 10 seconds (an infinite loop or very slow code)."
    if res["kind"] == "killed":
        return "The tests were killed for using too much memory or too many processes."
    out = res.get("output") or res.get("tail") or ""
    for marker in ("= FAILURES =", "= ERRORS ="):
        i = out.find(marker)
        if i >= 0:
            out = out[i:]
            break
    out = "\n".join(line for line in out.splitlines() if not line.startswith("platform ") and "rootdir:" not in line)
    return out[:FEEDBACK_CHARS].strip() or "The tests failed."


def feedback_message(ext: dict, res: dict | None) -> str:
    n = f" ({res['passed']} passed, {res['failed']} failed)" if res and res.get("failed") is not None else ""
    return (f"Your solution was run against some of the tests and did not pass{n}. What the tests reported:\n\n"
            f"{failure_text(ext, res)}\n\nFix the code. Reply with the complete corrected solution in a single fenced python block, "
            "in the same format as before.")


def messages_for(task: dict, attempts: list) -> list:
    """The prompt plus, for every earlier attempt, the model's answer and the feedback on it."""
    msgs = cr.prompt_for(task)
    for a in attempts:
        body = f"```python\n{a['code']}\n```" if a.get("code") else (a.get("detail") or "(no usable answer)")
        msgs += [{"role": "assistant", "content": body}, {"role": "user", "content": feedback_message(a, a.get("vis"))}]
    return msgs


def vis_ok(a: dict) -> bool:
    return bool(a.get("code")) and not a.get("failure") and bool(a.get("vis")) and a["vis"]["kind"] == "ok"


def verdict(one_shot: int, loop: int, accepted: int, accepted_ok: int, complete: bool) -> tuple[str, str]:
    """(PASS|NO-NEED|FAIL|not run, reason). Criteria fixed in HYPOTHESIS-write-code.md: trust A = at least 85% of the
    accepted tasks pass every held-out test; lift B = at least 3 more tasks solved than one shot; NO-NEED = one shot
    already solves 23 or more and A holds."""
    if not complete:
        return "not run", "one-shot results incomplete"
    trust = accepted_ok / accepted if accepted else 0.0
    a = accepted > 0 and trust >= 0.85
    b = loop - one_shot >= 3
    if a and b:
        return "PASS", f"trust {trust:.0%}, lift {loop - one_shot:+d}"
    if a and one_shot >= 23:
        return "NO-NEED", f"one shot solves {one_shot}/25, trust {trust:.0%}"
    why = []
    if not a:
        why.append(f"trust {trust:.0%} below 85%" if accepted else "nothing accepted")
    if not b:
        why.append(f"lift {loop - one_shot:+d} below +3")
    return "FAIL", ", ".join(why)


# ---------------------------------------------------------------- one model
class Ctx:
    """A model on its machine: loaded on first need and released whenever the sandbox is not available."""

    def __init__(self, cfg, machine: str, args, deadline: float):
        self.cfg = replace(cfg, timeout=max(cfg.timeout, args.min_timeout))
        self.machine, self.args, self.deadline = machine, args, deadline
        self.is_night = machine == args.night_ssh
        self.cleanup = None
        self.env = {k: v for k, v in os.environ.items() if k != "MINION_QUIET_WINDOWS"}

    def quiet(self) -> bool:
        return cr.night_quiet(self.args.docker_host, self.args.night_windows)[0]

    def ready(self) -> bool:
        if self.cfg.cloud:
            return True
        if self.is_night and not self.quiet():
            self.release()
            return False
        if self.cleanup is None:
            cleanup, skip = cr.prepare_local(self.cfg, self.machine, self.env, min(self.deadline, time.time() + 120))
            if cleanup is None:
                log(f"{self.cfg.name}: loop deferred ({skip})")
                return False
            self.cleanup = cleanup
        return True

    def release(self) -> None:
        if self.cleanup:
            try:
                self.cleanup()
            except MinionError as e:
                log(f"{self.cfg.name}: unload failed ({e})")
            self.cleanup = None

    def generate(self, msgs: list) -> dict:
        def call():
            res, lat, e = modelfit.attempt(lambda: backends.complete_ex(self.cfg, msgs, None, max_tokens=self.args.max_tokens))
            if e:
                return {"error": e.code, "detail": str(e)[:200], "latency": round(lat, 2)}
            raw, finish = res
            return {"latency": round(lat, 2), **cr.extract_code(raw, finish)}
        if self.is_night:
            with cr.NIGHT_LOCK:
                return call()
        return call()


def sb_run(ctx: Ctx, sb, tid: str, code: str, tb: str = "no") -> dict | None:
    """One sandbox run if the night host is quiet right now, else None (the caller defers; nothing stays loaded)."""
    if not ctx.quiet():
        ctx.release()
        return None
    with cr.NIGHT_LOCK:
        res = sb.run(tid, code, tb)
    if res["kind"] == "sandbox_error":
        log(f"sandbox error for {ctx.cfg.name}/{tid}: {res.get('stderr') or res.get('tail')}; will retry later")
        return None
    return res


def process_task(ctx: Ctx, sb, task: dict, gen_rec: dict, entry: dict, save) -> str:
    """Advance one task as far as possible. 'done', or 'deferred' (sandbox or model not available right now)."""
    tid = task["id"]
    atts = entry.setdefault("attempts", [])
    if not atts:
        atts.append({"n": 1, "code": gen_rec.get("code"), "failure": gen_rec.get("failure"), "detail": gen_rec.get("detail", ""),
                     "latency": gen_rec.get("latency")})
    while True:
        a = atts[-1]
        if "vis" not in a and a.get("code") and not a.get("failure"):
            res = sb_run(ctx, sb, f"{tid}_vis", a["code"], "short")
            if res is None:
                return "deferred"
            a["vis"] = {k: res.get(k) for k in ("kind", "passed", "failed", "output", "tail")}
            save()
        if vis_ok(a) or len(atts) >= MAX_ATTEMPTS:
            break
        if not ctx.ready():
            return "deferred"
        rec = ctx.generate(messages_for(task, atts))
        if rec.get("error"):
            if rec["error"] in cr.DEAD:
                return "deferred"
            rec = {"code": None, "failure": "generation_error", "detail": rec["error"], "latency": rec["latency"]}
        atts.append({"n": len(atts) + 1, **{k: rec.get(k) for k in ("code", "failure", "detail", "latency")}})
        save()
    entry["accepted"] = vis_ok(atts[-1])
    final = atts[-1]
    if "final" not in entry:
        if final.get("code") and not final.get("failure"):
            full = sb_run(ctx, sb, tid, final["code"])
            hold = sb_run(ctx, sb, f"{tid}_hold", final["code"]) if full else None
            if full is None or hold is None:
                return "deferred"
            entry["final"] = {"full": {k: full.get(k) for k in ("kind", "passed", "failed")},
                              "hold": {k: hold.get(k) for k in ("kind", "passed", "failed")}}
        else:
            entry["final"] = {"full": None, "hold": None}
    entry["done"] = True
    save()
    return "done"


def loop_model(cfg, machine: str, run: Path, loopdir: Path, tasks: list, sb, args, deadline: float) -> str:
    gp = run / "gen" / f"{cfg.name}.json"
    if not gp.exists():
        return "deferred"
    gen = json.loads(gp.read_text())
    if gen.get("unavailable"):
        return "done"
    if any(t["id"] not in gen["tasks"] or gen["tasks"][t["id"]].get("error") for t in tasks):
        return "deferred"          # one-shot results incomplete: wait for them, never score the gap
    path = loopdir / f"{cfg.name}.json"
    doc = json.loads(path.read_text()) if path.exists() else {"model": cfg.name, "cloud": cfg.cloud, "tasks": {}}
    ctx = Ctx(cfg, machine, args, deadline)
    result = "done"
    try:
        for t in tasks:
            entry = doc["tasks"].setdefault(t["id"], {})
            if entry.get("done"):
                continue
            if process_task(ctx, sb, t, gen["tasks"][t["id"]], entry, lambda: modelfit.save(path, doc)) == "deferred":
                result = "deferred"
                break
            log(f"loop {cfg.name}/{t['id']}: {len(entry['attempts'])} attempt(s), accepted={entry['accepted']}")
    finally:
        modelfit.save(path, doc)
        ctx.release()
    return result


def loop_group(cfgs: list, machine: str, run: Path, loopdir: Path, tasks: list, sb, args, deadline: float) -> None:
    pending = list(cfgs)
    while pending and time.time() < deadline:
        for cfg in list(pending):
            if loop_model(cfg, machine, run, loopdir, tasks, sb, args, deadline) == "done":
                pending.remove(cfg)
        if pending:
            time.sleep(min(cr.POLL_S, max(1, deadline - time.time())))
    for cfg in pending:
        log(f"loop {cfg.name}: not finished before the deadline")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roster", default=os.environ.get("MINION_ROSTER"))
    ap.add_argument("--run", required=True, help="the code_run.py results folder (one-shot answers are read from there)")
    ap.add_argument("--env-file", action="append", default=[])
    ap.add_argument("--models")
    ap.add_argument("--remote", action="append", default=[], metavar="PORT=SSHHOST")
    ap.add_argument("--docker-host", default=os.environ.get("CODEBENCH_DOCKER_HOST"))
    ap.add_argument("--night-windows", default=cr.NIGHT_WINDOWS)
    ap.add_argument("--deadline-h", type=float, default=24.0)
    ap.add_argument("--max-tokens", type=int, default=cr.MAX_TOKENS)
    ap.add_argument("--min-timeout", type=int, default=cr.MIN_TIMEOUT_S)
    args = ap.parse_args()
    run = Path(args.run)
    loopdir = run / "loop"
    loopdir.mkdir(exist_ok=True)
    modelfit.LOG_FILE = run / "loop.log"
    modelfit.load_env_files(args.env_file)
    deadline = time.time() + args.deadline_h * 3600
    tasks = code_tasks.TASKS
    sb = sandbox.Sandbox(args.docker_host)
    try:
        sb.check()
        files = {}
        for t in tasks:
            vis, hold = code_tasks.split_tests(t["tests"])
            files.update({t["id"]: t["tests"], f"{t['id']}_vis": vis, f"{t['id']}_hold": hold})
    except sandbox.SandboxUnavailable as e:
        sys.exit(f"STOP: no usable Docker sandbox ({e}). Nothing was run and no model was called.")
    st = run / "selftest.json"
    if not st.exists() or not json.loads(st.read_text()).get("ok"):
        sys.exit("STOP: no passing sandbox self-test in the run folder; run bench/code_run.py first.")
    # staging copies test files to the night host: only inside its window
    if not cr.wait_until(lambda: cr.night_quiet(args.docker_host, args.night_windows), "staging test files", deadline):
        sys.exit("STOP: the night host was never quiet before the deadline")
    sb.stage(files)
    raw = json.loads(Path(args.roster).expanduser().read_text())
    models, _ = cr.text_models(Roster.from_dict({"models": raw["models"]}))
    if args.models:
        models = [m for m in models if m.name in args.models.split(",")]
    remote = {int(p): h for p, h in (x.split("=") for x in args.remote)}
    groups = defaultdict(list)
    for cfg in models:
        port = urlparse(cfg.base_url).port
        groups[("cloud", urlparse(cfg.base_url).hostname) if cfg.cloud else (remote.get(port, "local"), "")].append(cfg)
    args.night_ssh = args.docker_host or ""
    log(f"loop: models {[m.name for m in models]}")
    with ThreadPoolExecutor(len(groups)) as ex:
        futs = [ex.submit(loop_group, cfgs, "local" if k[0] == "cloud" else k[0], run, loopdir, tasks, sb, args, deadline)
                for k, cfgs in groups.items()]
        for f in futs:
            f.result()
    log("loop done")


if __name__ == "__main__":
    main()
