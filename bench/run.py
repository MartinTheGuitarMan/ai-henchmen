"""Model-fit trial: run every roster model on the same invented test set (bench/dataset.py) and record raw results.

Scoring is done here in code against known answers, never by a model. bench/report.py turns the results into tables.

    uv run python bench/run.py --roster ROSTER.json --out bench/results/RUN [--extra EXTRA.json] [--env-file F ...]
        [--models a,b] [--tools grounded,same] [--remote PORT=SSHHOST ...] [--max-wait-h 2] [--redo]

Privacy: a local model is called with sensitive=true (so the privacy gate applies); a cloud model is called with
sensitive=false and only ever sees the invented public text of the dataset.

Quiet machine: before a local model is first used, the same gate as docs/dynamic-models.md runs (free memory, memory
pressure, power, hold marker). A refused model waits and is retried every 5 minutes up to --max-wait-h hours, then is
recorded as skipped with the reason. Models the bench loaded itself are unloaded again at the end. Results are written
after every (model, tool) unit and finished units are skipped on a rerun, so a long run can be stopped and resumed.

The tools run exactly as the server runs them (quote check, evidence check, schema validation), with the roster
narrowed to the one model under test and `caps` lifted so every model is tried on every tool.
"""
from __future__ import annotations

import argparse
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
import dataset as D  # noqa: E402
from minions import lifecycle, tools  # noqa: E402
from minions.config import TOOLS, Roster, Route  # noqa: E402
from minions.errors import MinionDown, MinionError, RateLimited, SchemaError  # noqa: E402

BENCH_TOOLS = ("grounded", "same", "extract", "classify_batch", "tag_batch")
SERVES = {"grounded": "grounded", "same": "same", "extract": "extract", "classify_batch": "classify", "tag_batch": "tag"}
POLL_S = 300
LOG_LOCK = threading.Lock()
LOG_FILE: Path | None = None


def log(msg: str) -> None:
    line = f"{datetime.now():%H:%M:%S} {msg}"
    with LOG_LOCK:
        print(line, flush=True)
        if LOG_FILE:
            with LOG_FILE.open("a") as f:
                f.write(line + "\n")


def load_env_files(paths: list[str]) -> None:
    for p in paths:
        for line in Path(p).expanduser().read_text().splitlines():
            m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
            if m and m[1] not in os.environ:
                os.environ[m[1]] = m[2].strip().strip("'\"")


def single_roster(cfg) -> Roster:
    m = replace(cfg, caps=None)
    return Roster({m.name: m}, {t: Route((m,), None, 1) for t in TOOLS if m.serves(t)}, 1_000_000, meta=True)


# ---------- the quiet-machine gate ----------
def ssh_runner(host: str):
    def run(cmd):
        if cmd not in lifecycle.ALLOWED:
            raise ValueError(cmd)
        try:
            r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, *cmd],
                               capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return r.stdout if r.returncode == 0 else None
    return run


def gate(machine: str, need_gb: float) -> dict:
    runner = ssh_runner(machine) if machine != "local" else None
    env = {k: v for k, v in os.environ.items() if k != "MINION_QUIET_WINDOWS"}   # the bench is a deliberate job
    probes = lifecycle.local_probes(env=env, runner=runner)
    mem = (runner or lifecycle.run_command)(("sysctl", "-n", "hw.memsize"))
    total = int(mem.strip()) / lifecycle.GB if mem and mem.strip().isdigit() else None
    return lifecycle.gate(probes, need_gb=need_gb, total_gb=total, min_free_pct=int(env.get("MINION_MIN_FREE_PCT", "45")),
                          allow_battery=env.get("MINION_ALLOW_BATTERY") == "1")


def busy_now(machine: str) -> list:
    return [r for r in gate(machine, 0.0)["reasons"] if r.startswith("hold") or "pressure" in r]


def ollama_root(cfg) -> str | None:
    return cfg.base_url.removesuffix("/v1") if cfg.backend == "ollama" else None


def http_json(url: str, body: dict | None = None):
    import httpx
    try:
        r = httpx.post(url, json=body, timeout=30) if body is not None else httpx.get(url, timeout=10)
        return r.json()
    except Exception:
        return None


def model_size_gb(cfg) -> float:
    root = ollama_root(cfg)
    data = http_json(f"{root}/api/tags") if root else None
    for m in (data or {}).get("models", []):
        if m.get("name") == cfg.model or m.get("model") == cfg.model:
            return round(m.get("size", 0) / lifecycle.GB, 1)
    return 0.0


def resident(cfg) -> set:
    root = ollama_root(cfg)
    data = http_json(f"{root}/api/ps") if root else None
    return {m.get("name") for m in (data or {}).get("models", [])}


# ---------- one item ----------
def attempt(fn, patience: int = 6):
    """Call fn(); wait out rate limits (never scored as wrong). Returns (result, latency_s, error or None)."""
    last = None
    for _ in range(patience):
        t = time.time()
        try:
            return fn(), time.time() - t, None
        except RateLimited as e:
            last = e
            time.sleep(min((e.retry_after or 20) + 0.5, 70))
        except MinionError as e:
            return None, time.time() - t, e
    return None, 0.0, last


def err_rec(e: MinionError) -> dict:
    return {"error": e.code, "detail": str(e)[:160]}


def norm(v):
    return " ".join(v.split()).lower() if isinstance(v, str) else v


def field_ok(got, want) -> bool:
    if isinstance(want, list):
        return any(field_ok(got, w) for w in want)
    if isinstance(want, bool) or isinstance(got, bool):
        return got is want
    if isinstance(want, (int, float)):
        return isinstance(got, (int, float)) and abs(float(got) - float(want)) < 1e-6
    return norm(got) == norm(want)


def item_grounded(roster, sens, g):
    out, lat, e = attempt(lambda: tools.grounded(roster, g["claim"], g["source"], sensitive=sens))
    rec = {"tag": g["tag"], "expected": g["expected"], "latency": lat}
    if e:
        return {**rec, **err_rec(e), "ok": False}
    meta = out.get("_minion", {})
    raw = meta.get("downgraded") or out["verdict"]
    return {**rec, "got": out["verdict"], "raw": raw, "quote_survived": raw in ("supported", "contradicted") and "downgraded" not in meta,
            "ok": out["verdict"] == g["expected"]}


def item_same(roster, sens, s):
    out, lat, e = attempt(lambda: tools.same(roster, s["a"], s["b"], sensitive=sens))
    rec = {"tag": s["tag"], "expected": s["expected"], "latency": lat}
    if e:
        return {**rec, **err_rec(e), "ok": False, "evidence_fail": "no evidence" in str(e)}
    return {**rec, "got": out["verdict"], "ok": out["verdict"] == s["expected"]}


def item_extract(roster, sens, x):
    out, lat, e = attempt(lambda: tools.extract(roster, x["text"], x["schema"], hint=x["hint"], sensitive=sens))
    rec = {"tag": x["tag"], "latency": lat}
    if e:
        return {**rec, **err_rec(e), "ok": False, "fields": 0, "fields_total": len(x["expected"])}
    good = {k: field_ok(out.get(k), v) for k, v in x["expected"].items()}
    return {**rec, "got": {k: out.get(k) for k in x["expected"]}, "ok": all(good.values()),
            "fields": sum(good.values()), "fields_total": len(good)}


def batch_one(fn, text):
    """One-item batch through the real batch tool. Returns (result dict or None, latency, error code/detail dict).
    A rate limit reported inside the batch result is waited out and retried, like one raised by a single call."""
    for _ in range(8):
        res, lat, e = attempt(lambda: fn([{"id": "0", "text": text}]))
        if e:
            return None, lat, err_rec(e)
        r = res["results"][0]
        if "error" not in r:
            return r, lat, None
        if r["error"]["code"] == "MINION_RATE_LIMITED":
            time.sleep(min(r["error"].get("retry_after", 20) + 0.5, 70))
            continue
        return None, lat, {"error": r["error"]["code"], "detail": r["error"]["message"][:160]}
    return None, 0.0, {"error": "MINION_RATE_LIMITED", "detail": "still limited after 8 waits"}


def item_classify(roster, sens, c):
    r, lat, e = batch_one(lambda items: tools.classify_batch(roster, items, D.TICKET_LABELS, sensitive=sens), c["text"])
    rec = {"tag": c["tag"], "latency": lat}
    if "expected_error" in c:
        return {**rec, "expected": c["expected_error"], "got": (e or {}).get("error", "no error"),
                "ok": bool(e) and e["error"] == c["expected_error"]}
    if e:
        return {**rec, "expected": c["expected"], **e, "ok": False}
    return {**rec, "expected": c["expected"], "got": r["label"], "ok": r["label"] == c["expected"]}


def item_tag(roster, sens, t):
    r, lat, e = batch_one(lambda items: tools.tag_batch(roster, items, D.TAG_LABELS, D.TAG_MAX, sensitive=sens), t["text"])
    rec = {"tag": t["tag"], "latency": lat}
    if "expected_error" in t:
        return {**rec, "expected": t["expected_error"], "got": (e or {}).get("error", "no error"),
                "ok": bool(e) and e["error"] == t["expected_error"]}
    want = set(t["expected"])
    if e:
        return {**rec, "expected": sorted(want), **e, "ok": False, "missed": len(want), "spurious": 0}
    got = set(r["labels"])
    return {**rec, "expected": sorted(want), "got": sorted(got), "ok": got == want,
            "missed": len(want - got), "spurious": len(got - want)}


UNITS = {
    "grounded": (D.GROUNDED, item_grounded),
    "same": (D.SAME, item_same),
    "extract": (D.EXTRACT, item_extract),
    "classify_batch": (D.CLASSIFY + D.BAD_ITEMS, item_classify),
    "tag_batch": (D.TAG + [{**b, "expected": []} for b in D.BAD_ITEMS], item_tag),
}
DEAD = ("MINION_DOWN", "MINION_BACKEND_ERROR")


def run_unit(roster, sens, tool: str) -> dict:
    data, fn = UNITS[tool]
    items, dead_run = [], 0
    for d in data:
        rec = fn(roster, sens, d)
        items.append(rec)
        dead_run = dead_run + 1 if rec.get("error") in DEAD else 0
        if dead_run >= 3 and len(items) == dead_run:
            return {"status": "unavailable", "reason": rec.get("detail", rec["error"]), "items": items}
        if sum(r.get("error") == "MINION_RATE_LIMITED" for r in items[-3:]) == 3:
            return {"status": "rate_limited_out", "reason": "provider kept refusing (quota?)", "items": items}
    lats = [r["latency"] for r in items if r["latency"]]
    return {"status": "done", "items": items,
            "p50": statistics.median(lats) if lats else None,
            "p95": sorted(lats)[max(0, int(len(lats) * 0.95 + 0.5) - 1)] if lats else None}


def save(path: Path, doc: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1, default=str))
    tmp.replace(path)


def work_machine(cfgs: list, machine: str, out: Path, tools_wanted, redo: bool, max_wait_h: float) -> None:
    for cfg in cfgs:
        path = out / f"{cfg.name}.json"
        doc = json.loads(path.read_text()) if path.exists() and not redo else \
            {"model": cfg.name, "backend_model": cfg.model, "cloud": cfg.cloud, "kind": cfg.kind, "machine": machine, "units": {}}
        roster, sens = single_roster(cfg), not cfg.cloud
        todo = [t for t in tools_wanted if roster.models[cfg.name].serves(SERVES[t])
                and (cfg.kind != "decision" or t == "classify_batch")   # decision models give a label only: no quote, no evidence
                and doc["units"].get(t, {}).get("status") != "done"]
        if not todo:
            continue
        we_loaded = False
        if not cfg.cloud:
            size, before = model_size_gb(cfg), resident(cfg)
            waited = 0.0
            while True:
                g = gate(machine, size)
                if g["allowed"]:
                    break
                log(f"{cfg.name}: gate refuses ({'; '.join(g['reasons'])}); waiting")
                if waited >= max_wait_h * 3600:
                    doc["units"].update({t: {"status": "skipped", "reason": "; ".join(g["reasons"]), "items": []} for t in todo})
                    save(path, doc)
                    break
                time.sleep(POLL_S)
                waited += POLL_S
            else_skip = doc["units"].get(todo[0], {}).get("status") == "skipped"
            if else_skip:
                continue
            we_loaded = cfg.model not in before
        for t in todo:
            while not cfg.cloud and (busy := busy_now(machine)):   # our own model uses memory, so only hold/pressure count
                log(f"{cfg.name}/{t}: machine busy ({'; '.join(busy)}); pausing")
                time.sleep(POLL_S)
            log(f"{cfg.name}/{t}: start")
            doc["units"][t] = run_unit(roster, sens, t)
            u = doc["units"][t]
            ok = sum(r["ok"] for r in u["items"])
            log(f"{cfg.name}/{t}: {u['status']} {ok}/{len(u['items'])}" + (f" ({u.get('reason')})" if u.get("reason") else ""))
            save(path, doc)
            if u["status"] == "unavailable" and all(r.get("error") in DEAD for r in u["items"]):
                for rest in todo[todo.index(t) + 1:]:
                    doc["units"][rest] = {"status": "unavailable", "reason": u["reason"], "items": []}
                save(path, doc)
                break
        if we_loaded and (root := ollama_root(cfg)):
            http_json(f"{root}/api/generate", {"model": cfg.model, "keep_alive": 0})   # unload what this run loaded
            log(f"{cfg.name}: unloaded")


def main() -> None:
    global LOG_FILE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roster", default=os.environ.get("MINION_ROSTER"))
    ap.add_argument("--extra", help="JSON file with more models ({\"models\": {...}}) to try beside the roster")
    ap.add_argument("--env-file", action="append", default=[], help="KEY=VALUE file with API keys (not printed)")
    ap.add_argument("--models")
    ap.add_argument("--tools", default=",".join(BENCH_TOOLS))
    ap.add_argument("--remote", action="append", default=[], metavar="PORT=SSHHOST",
                    help="a local model on this port runs on another machine; gate it there over ssh")
    ap.add_argument("--max-wait-h", type=float, default=2.0)
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if not a.roster:
        sys.exit("--roster or MINION_ROSTER is required")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    LOG_FILE = out / "run.log"
    load_env_files(a.env_file)
    raw = json.loads(Path(a.roster).expanduser().read_text())
    models = dict(raw["models"])
    if a.extra:
        for k, v in json.loads(Path(a.extra).read_text())["models"].items():
            models.setdefault(k, v)
    roster = Roster.from_dict({"models": models})
    want = a.models.split(",") if a.models else [n for n, m in roster.models.items() if m.kind != "reasoning"]
    remote = {int(p): h for p, h in (x.split("=") for x in a.remote)}
    groups = defaultdict(list)
    for n in want:
        cfg = roster.models[n]
        host = urlparse(cfg.base_url).hostname
        port = urlparse(cfg.base_url).port
        groups[("cloud", host) if cfg.cloud else (remote.get(port, "local"), "")].append(cfg)
    tools_wanted = [t for t in a.tools.split(",") if t in BENCH_TOOLS]
    log(f"models: {len(want)}, tools: {tools_wanted}, groups: {[(k[0] if k[0] != 'cloud' else k[1]) for k in groups]}")
    with ThreadPoolExecutor(len(groups)) as ex:
        futs = [ex.submit(work_machine, cfgs, "local" if k[0] == "cloud" else k[0], out, tools_wanted, a.redo, a.max_wait_h)
                for k, cfgs in groups.items()]
        for f in futs:
            f.result()
    log("done")


if __name__ == "__main__":
    main()
