"""Markdown report of the write_code retry-loop eval (bench/code_loop.py). Per model: one shot vs the loop, trust of the
accepted answers on held-out tests, and the verdict by the criteria of HYPOTHESIS-write-code.md.

    uv run python bench/code_loop_report.py bench/results/RUN > bench/results/RUN/LOOP.md
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import code_loop  # noqa: E402
import code_report  # noqa: E402
import code_tasks  # noqa: E402

N = len(code_tasks.TASKS)


def ok_all(r: dict | None) -> bool:
    return bool(r) and r.get("kind") == "ok"


def model_row(one: dict, doc: dict | None) -> dict:
    """Numbers for one model. `one` is a code_report.load() row, `doc` the loop file (None if not started)."""
    s = code_report.summary(one)
    row = {"model": one["model"], "one_solved": s["solved"], "one_tests": f"{s['passed']}/{s['total']}", "n_one": s["n"]}
    done = [t for t in code_tasks.TASKS if doc and doc["tasks"].get(t["id"], {}).get("done")]
    row["n_done"] = len(done)
    if len(done) < N or s["n"] < N:
        row.update(complete=False)
        return row
    loop_solved = accepted = acc_ok = fixed = retried = 0
    tests = total = 0
    extra = []
    for t in code_tasks.TASKS:
        e = doc["tasks"][t["id"]]
        f = e["final"]
        full_ok = bool(f["full"]) and ok_all(f["full"]) and f["full"]["passed"] == t["n_tests"]
        loop_solved += full_ok
        tests += min(f["full"]["passed"], t["n_tests"]) if f["full"] else 0
        total += t["n_tests"]
        if e["accepted"]:
            accepted += 1
            acc_ok += ok_all(f["hold"])
        if len(e["attempts"]) > 1:
            retried += 1
            fixed += full_ok
            extra.append(sum(a.get("latency") or 0 for a in e["attempts"][1:]))
    v, why = code_loop.verdict(s["solved"], loop_solved, accepted, acc_ok, True)
    row.update(complete=True, loop_solved=loop_solved, loop_tests=f"{tests}/{total}", accepted=accepted, acc_ok=acc_ok,
               retried=retried, fixed=fixed, extra=statistics.median(extra) if extra else 0.0, verdict=v, why=why)
    return row


def main(run: Path) -> None:
    rows = {r["model"]: r for r in code_report.load(run)}
    loopdir = run / "loop"
    docs = {p.stem: json.loads(p.read_text()) for p in sorted(loopdir.glob("*.json"))} if loopdir.exists() else {}
    md = ["# write_code retry-loop eval", "",
          f"{N} tasks. Attempt 1 is the stored one-shot answer; visible tests drive up to 3 attempts; the final code is scored on "
          "all hidden tests and on the held-out half alone. One task is 4 points, so differences of one or two tasks are noise.", "",
          "| model | one shot (tasks / tests) | loop (tasks / tests) | change | accepted | trust: accepted that pass every held-out test | retried -> fixed | median extra s | verdict |",
          "|---|---|---|---|---|---|---|---|---|"]
    notrun = []
    for name, one in rows.items():
        if not one["per"]:
            notrun.append(f"- {name}: no one-shot results, so no loop run ({one['note']})")
            continue
        r = model_row(one, docs.get(name))
        if not r["complete"]:
            notrun.append(f"- {name}: not run yet or incomplete ({r['n_done']}/{N} tasks looped, {r['n_one']}/{N} one-shot results). No verdict.")
            continue
        trust = f"{r['acc_ok']}/{r['accepted']} ({r['acc_ok'] / r['accepted']:.0%})" if r["accepted"] else "-"
        md.append(f"| {name} | {r['one_solved']}/{N} ({r['one_tests']}) | {r['loop_solved']}/{N} ({r['loop_tests']}) | "
                  f"{r['loop_solved'] - r['one_solved']:+d} | {r['accepted']}/{N} | {trust} | {r['retried']} -> {r['fixed']} | "
                  f"{r['extra']:.0f} | **{r['verdict']}** ({r['why']}) |")
    md += ["", *notrun]
    print("\n".join(md))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
