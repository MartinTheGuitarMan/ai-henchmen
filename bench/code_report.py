"""Turn the results of bench/code_run.py into the coding-bench report (markdown on stdout).

    uv run python bench/code_report.py bench/results/RUN > bench/results/RUN/RESULTS.md

Includes HYPOTHESIS.md (written before the run, never edited afterwards) and READING.md (the honest reading afterwards)
from the same folder when they exist. Scoring is pass@1: hidden tests passed out of total, and fully solved tasks.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import code_run  # noqa: E402
import code_tasks  # noqa: E402

LEVELS = ("easy", "medium", "hard")
KINDS = ("write", "fix", "regex")
FAILURES = ("generation_error", "no_code_block", "truncated", "syntax_error", "import_error", "timeout", "killed",
            "wrong_answer", "not_run")


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({100 * a / b:.0f}%)" if b else "-"


def load(out: Path) -> list[dict]:
    rows = []
    for gp in sorted((out / "gen").glob("*.json")):
        g = json.loads(gp.read_text())
        ep = out / "exec" / gp.name
        e = json.loads(ep.read_text()) if ep.exists() else {"tasks": {}}
        per, lat = {}, []
        for t in code_tasks.TASKS:
            rec = g["tasks"].get(t["id"])
            if rec is None:
                continue
            if rec.get("error"):
                per[t["id"]] = {"passed": 0, "total": t["n_tests"], "solved": False, "failure": "generation_error"}
                continue
            lat.append(rec["latency"])
            ext = {"failure": rec.get("failure")}
            run = e["tasks"].get(t["id"])
            per[t["id"]] = code_run.score(t, ext, run)
        rows.append({"model": g["model"], "cloud": g["cloud"], "machine": g["machine"], "backend_model": g.get("backend_model"),
                     "per": per, "lat": lat, "note": g.get("note") or g.get("skipped") or g.get("unavailable")})
    return rows


def summary(r: dict) -> dict:
    per = r["per"]
    n = len(per)
    s = {"n": n, "solved": sum(v["solved"] for v in per.values()),
         "passed": sum(v["passed"] for v in per.values()), "total": sum(v["total"] for v in per.values())}
    s["rate"] = s["passed"] / s["total"] if s["total"] else 0.0
    return s


def by(r: dict, attr: str, value: str) -> tuple[int, int, int, int]:
    ids = [t["id"] for t in code_tasks.TASKS if t[attr] == value and t["id"] in r["per"]]
    return (sum(r["per"][i]["solved"] for i in ids), len(ids),
            sum(r["per"][i]["passed"] for i in ids), sum(r["per"][i]["total"] for i in ids))


def p(xs: list, q: float):
    return sorted(xs)[max(0, int(len(xs) * q + 0.5) - 1)] if xs else None


def main(out: Path) -> None:
    rows = load(out)
    notes = json.loads((out / "notes.json").read_text()) if (out / "notes.json").exists() else {"notes": [], "models": []}
    st = json.loads((out / "selftest.json").read_text()) if (out / "selftest.json").exists() else None
    ntasks = len(code_tasks.TASKS)
    md = [f"# Coding bench: {out.name}", ""]
    md.append(f"{ntasks} invented Python tasks with hidden pytest tests ({sum(t['n_tests'] for t in code_tasks.TASKS)} tests in all): "
              f"{sum(t['kind'] == 'write' for t in code_tasks.TASKS)} write-a-function, "
              f"{sum(t['kind'] == 'fix' for t in code_tasks.TASKS)} bug-fix, {sum(t['kind'] == 'regex' for t in code_tasks.TASKS)} regex; "
              f"{sum(t['level'] == 'easy' for t in code_tasks.TASKS)} easy, {sum(t['level'] == 'medium' for t in code_tasks.TASKS)} medium, "
              f"{sum(t['level'] == 'hard' for t in code_tasks.TASKS)} hard. One shot, temperature 0, one fenced Python block extracted in code, "
              "no retries (pass@1). Model code ran only in a Docker sandbox (no network, read-only filesystem, non-root, "
              "limited CPU/memory/processes, 10 s). Scoring is done in code. Local models ran with sensitive=true; cloud models "
              "(sensitive=false) saw only these invented public tasks.")
    md.append("")
    md.append(f"**Reading the numbers:** one task is {100 / ntasks:.0f} points of 'solved', and a single run at temperature 0 is one sample, "
              "so differences of one or two tasks are noise. Test-level pass rate is finer but not independent of the task count.")
    if st and "probes_passed" in st:
        md.append(f"\nSandbox self-test (a known-bad snippet that tries the network, writes outside its tmpfs, runs as root, forks without limit, "
                  f"fills the disk, hangs or eats memory): {st['probes_passed']} probes blocked, infinite loop {st['hang_kind']}, "
                  f"memory hog {st['mem_kind']}, good snippet passes: {st['good_snippet_passes']}.")
    hyp = out / "HYPOTHESIS.md"
    if hyp.exists():
        md += ["", "## Hypothesis (written before the run)", "", hyp.read_text().strip()]
    md += ["", "## Overall", "",
           "| model | where | solved | tests passed | easy | medium | hard | failures | p50 s | p95 s |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    ranked = sorted(rows, key=lambda r: (-summary(r)["rate"], -summary(r)["solved"]))
    for r in ranked:
        s = summary(r)
        lv = [by(r, "level", l) for l in LEVELS]
        fails = sum(1 for v in r["per"].values() if not v["solved"])
        md.append(f"| {r['model']} | {'cloud' if r['cloud'] else 'local'} | {pct(s['solved'], s['n'])} | {pct(s['passed'], s['total'])} | "
                  + " | ".join(f"{a}/{b}" for a, b, _, _ in lv) + f" | {fails} | "
                  + (f"{statistics.median(r['lat']):.1f} | {p(r['lat'], .95):.1f} |" if r["lat"] else "- | - |"))
    partial = [r["model"] for r in rows if len(r["per"]) < ntasks]
    if partial:
        md.append(f"\nIncomplete (fewer than {ntasks} tasks scored so far): " + ", ".join(f"{r['model']} ({len(r['per'])}/{ntasks})" for r in rows if len(r['per']) < ntasks))
    for r in rows:
        if r["note"] and not r["per"]:
            md.append(f"- Not run: {r['model']}: {r['note']}")
        elif r["note"]:
            md.append(f"- {r['model']}: {r['note']}")
    for n in notes["notes"]:
        md.append(f"- Left out: {n}")
    full = [r for r in ranked if len(r["per"]) == ntasks]
    if full:
        loc = [r for r in full if not r["cloud"]]
        md += ["", f"- **Best overall:** {full[0]['model']} ({pct(summary(full[0])['passed'], summary(full[0])['total'])} of tests, "
                   f"{summary(full[0])['solved']}/{ntasks} tasks solved)"]
        if loc:
            md.append(f"- **Best local:** {loc[0]['model']} ({pct(summary(loc[0])['passed'], summary(loc[0])['total'])} of tests, "
                      f"{summary(loc[0])['solved']}/{ntasks} tasks solved)")
        tied = [r['model'] for r in full[1:] if summary(r)["solved"] >= summary(full[0])["solved"] - 1]
        if tied:
            md.append("- Within one task of the best (do not rank these against each other): " + ", ".join(tied))
    md += ["", "## By task type", "", "| model | " + " | ".join(KINDS) + " |", "|---|" + "---|" * len(KINDS)]
    for r in ranked:
        md.append(f"| {r['model']} | " + " | ".join(f"{a}/{b} tasks, {pct(c, d)} tests" for a, b, c, d in (by(r, 'kind', k) for k in KINDS)) + " |")
    md += ["", "## Failure kinds (tasks not fully solved)", "", "| model | " + " | ".join(FAILURES) + " |", "|---|" + "---|" * len(FAILURES)]
    for r in ranked:
        cnt = {f: sum(v["failure"] == f for v in r["per"].values()) for f in FAILURES}
        md.append(f"| {r['model']} | " + " | ".join(str(cnt[f] or "") for f in FAILURES) + " |")
    md.append("\n`wrong_answer` = the code ran and some tests failed. `import_error` = the module did not import or lacked the requested name. "
              "`killed` = out of memory or process limit. `not_run` = code waiting for the sandbox.")
    md += ["", "## Per task", "", "Cell = tests passed / total (a full solve is marked ✓).", "",
           "| task | level | " + " | ".join(r["model"] for r in ranked) + " |", "|---|---|" + "---|" * len(ranked)]
    for t in code_tasks.TASKS:
        cells = []
        for r in ranked:
            v = r["per"].get(t["id"])
            cells.append("." if v is None else ("✓" if v["solved"] else f"{v['passed']}/{v['total']}" + (f" {v['failure'][:4]}" if v["failure"] and v["failure"] != "wrong_answer" else "")))
        md.append(f"| {t['id']} | {t['level']} | " + " | ".join(cells) + " |")
    rd = out / "READING.md"
    if rd.exists():
        md += ["", "## Reading, afterwards", "", rd.read_text().strip()]
    print("\n".join(md))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
