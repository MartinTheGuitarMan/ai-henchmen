"""Trial runner for route_task (criteria: docs/tool-trials.md, "route_task trial").

    uv run python scripts/route_trial.py run --roster roster.json --models typesafe-jev,air-jev-style,air-qwen --set a --out results/
    uv run python scripts/route_trial.py report --sets a,b results/*.jsonl

Each invented task is labelled with the route a careful person would pick; the label is fixed before any run and never changed
after a result. Scored in code: accuracy on the final route (after the escalation rule), critical misses (a task labelled
ask_human or top_model that ends on a cheaper automatic route; any ask_human task that ends elsewhere), and a plain
keyword baseline (`baseline`) on the same tasks. A model that is unreachable is recorded as not_run, never as a wrong answer.
Cloud models get sensitive=False (every task here is invented); local ones sensitive=True."""
from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from minions import route_task as rt  # noqa: E402
from minions.config import Roster  # noqa: E402
from minions.errors import Busy, MinionDown, MinionError, PrivacyRefused, RateLimited  # noqa: E402

CHEAP = ("minion_tool", "script", "haiku", "sonnet")   # the automatic routes below top_model

# ---- the keyword baseline: plain rules, first match wins, default sonnet. Written before the sets.
BASELINE_RULES = [
    ("ask_human", r"force[- ]?push|\bdelete\b|\bremove\b.*\b(backup|branch|repo|account)|\bdrop (table|database)|\bsend\b.*\b(email|mail|message)|"
                  r"\bpublish\b|\bpost\b.*\b(to|on)\b|\brotate\b|\bcredential|\bpassword|\bdeploy\b.*\bprod|\bpurchase|\bbuy\b|\bpay\b|"
                  r"\btransfer\b|rm -rf|\bwipe\b|\berase\b|\bpermission|\bapprove\b|\bunsubscribe\b|\bcancel\b"),
    ("script", r"\bcount\b|\bhow many\b|\bsum\b|\btotal\b|\baverage\b|\bcompute\b|\bcalculate\b|\bchecksum\b|\bsha\d*\b|\bwc\b|\bdisk usage\b|"
               r"\bsize of\b|\bwhat day\b|\bdays? (between|until)\b"),
    ("haiku", r"\bfind\b|\blist\b|\bgrep\b|\bsearch\b|\bfetch\b|\bdownload\b|\blocate\b|\bshow me all\b"),
    ("minion_tool", r"\bsummari[sz]e\b|\bclassify\b|\bextract\b|\btag\b|\btranslate\b|\bcategori[sz]e\b|\bproofread\b|\bcompare these\b"),
    ("top_model", r"\bdesign\b|\barchitect|\btrade-?offs?\b|\broot cause\b|\bstrategy\b|\bthreat\b|\bsecurity\b|\bwhy\b|\bplan\b"),
]


def baseline(task: str) -> str:
    low = task.lower()
    for route, pattern in BASELINE_RULES:
        if re.search(pattern, low):
            return route
    return "sonnet"


# ---- cases: {id, task, label}. Set A is the tuning-free first set; set B the fresh set, written after any fix.
SET_A: list = []
SET_B: list = []
SETS = {"a": SET_A, "b": SET_B}


# ---- scoring (pure functions of a label and a final route)
def correct(label: str, final: str) -> bool:
    return final == label


def critical_miss(label: str, final: str) -> bool:
    """A task labelled ask_human or top_model that did not stay as safe: ask_human anywhere else, top_model on a cheaper route."""
    if label == "ask_human":
        return final != "ask_human"
    return label == "top_model" and final in CHEAP


def pinned_roster(raw: dict, model: str) -> Roster:
    """A throwaway roster in memory: `model` alone answers the classify route that route_task borrows."""
    raw = copy.deepcopy(raw)
    raw["models"][model].pop("caps", None)
    raw.setdefault("routes", {})["classify"] = {"fast": [model]}
    return dataclasses.replace(Roster.from_dict(raw), meta=True)


def one_call(roster: Roster, case: dict, sensitive: bool) -> dict:
    t0 = time.time()
    rec = {"status": "ok", "final": None, "model_route": None, "confidence": None, "reason": None, "detail": ""}
    try:
        out = rt.route_task(roster, case["task"], sensitive=sensitive)
        rec.update(final=out["route"], model_route=out["model_route"], confidence=out["confidence"], reason=out["reason"])
    except MinionDown as e:   # route_task turns a down model into a top_model answer; this is only the setup check
        rec.update(status="not_run", reason="unreachable", detail=str(e)[:160])
    except (Busy, PrivacyRefused, RateLimited) as e:
        rec.update(status="not_run", reason=e.code, detail=str(e)[:160])
    except MinionError as e:
        rec.update(status="error", reason=e.code, detail=str(e)[:200])
    rec["latency_s"] = round(time.time() - t0, 2)
    return rec


def run(args) -> int:
    raw = json.loads(Path(args.roster).expanduser().read_text())
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = SETS[args.set]
    for model in [m for m in args.models.split(",") if m]:
        sensitive = not raw["models"][model].get("cloud", False)
        roster = pinned_roster(raw, model)
        path = out_dir / f"{model}.jsonl"
        for c in cases:
            rec = one_call(roster, c, sensitive)
            rec.update(model=model, set=args.set, case=c["id"], label=c["label"], ts=round(time.time()))
            with path.open("a") as f:
                f.write(json.dumps(rec) + "\n")
            print(f"{model} {c['id']}: label={c['label']} final={rec['final']} conf={rec['confidence']} {rec['reason'] or ''} {rec['latency_s']}s", file=sys.stderr)
    return 0


def pct(xs: list, q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(q * len(xs)))], 2)


def summarize(recs: list, cases: list) -> dict:
    done = [r for r in recs if r["status"] != "not_run"]
    ok = sum(correct(r["label"], r["final"] or rt.SAFE_ROUTE) for r in done)
    raw_ok = sum(r["model_route"] == r["label"] for r in done)
    misses = [r["case"] for r in done if critical_miss(r["label"], r["final"] or rt.SAFE_ROUTE)]
    return {"n": len(done), "ok": ok, "acc": ok / len(done) if done else 0.0, "raw_acc": raw_ok / len(done) if done else 0.0,
            "misses": misses, "escalated": sum(bool(r["reason"]) for r in done),
            "p50": pct([r["latency_s"] for r in done], 0.5), "p95": pct([r["latency_s"] for r in done], 0.95)}


def baseline_summary(cases: list) -> dict:
    finals = [(c["id"], c["label"], baseline(c["task"])) for c in cases]
    ok = sum(l == f for _, l, f in finals)
    return {"n": len(cases), "ok": ok, "acc": ok / len(cases) if cases else 0.0,
            "misses": [i for i, l, f in finals if critical_miss(l, f)]}


def report(args) -> int:
    by = defaultdict(list)
    for f in args.files:
        for line in Path(f).read_text().splitlines():
            r = json.loads(line)
            by[(r["model"], r["set"])].append(r)
    print("| who | set | n | accuracy | model's own pick | escalated | critical misses | p50 s | p95 s |")
    print("|---|---|---|---|---|---|---|---|---|")
    for st in args.sets.split(","):
        b = baseline_summary(SETS[st])
        print(f"| keyword baseline | {st} | {b['n']} | {b['ok']}/{b['n']} ({round(100 * b['acc'])}%) | - | - | {len(b['misses'])} {b['misses'] or ''} | - | - |")
        for (model, s), recs in sorted(by.items()):
            if s != st:
                continue
            m = summarize(recs, SETS[st])
            print(f"| {model} | {st} | {m['n']} | {m['ok']}/{m['n']} ({round(100 * m['acc'])}%) | {round(100 * m['raw_acc'])}% | {m['escalated']} | "
                  f"{len(m['misses'])} {m['misses'] or ''} | {m['p50']} | {m['p95']} |")
    for (model, s), recs in sorted(by.items()):
        for r in recs:
            if r["status"] == "ok" and r["final"] != r["label"]:
                print(f"  {model} {r['case']} label={r['label']} final={r['final']} model={r['model_route']} conf={r['confidence']} {r['reason'] or ''}")
            elif r["status"] != "ok":
                print(f"  {model} {r['case']} {r['status']} {r['reason']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--roster", required=True)
    r.add_argument("--models", required=True)
    r.add_argument("--set", choices=sorted(SETS), required=True)
    r.add_argument("--out", required=True)
    p = sub.add_parser("report")
    p.add_argument("--sets", default="a,b")
    p.add_argument("files", nargs="+")
    args = ap.parse_args(argv)
    return run(args) if args.cmd == "run" else report(args)


if __name__ == "__main__":
    sys.exit(main())
