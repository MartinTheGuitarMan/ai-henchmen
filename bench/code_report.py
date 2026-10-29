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
        per, lat, latd = {}, [], {}
        for t in code_tasks.TASKS:
            rec = None if g.get("unavailable") else g["tasks"].get(t["id"])   # an unavailable model is "not run", not "all wrong"
            if rec is None:
                continue
            if rec.get("error"):
                per[t["id"]] = {"passed": 0, "total": t["n_tests"], "solved": False, "failure": "generation_error"}
                continue
            lat.append(rec["latency"])
            latd[t["id"]] = rec["latency"]
            ext = {"failure": rec.get("failure")}
            run = e["tasks"].get(t["id"])
            per[t["id"]] = code_run.score(t, ext, run)
        rows.append({"model": g["model"], "cloud": g["cloud"], "machine": g["machine"], "backend_model": g.get("backend_model"),
                     "per": per, "lat": lat, "latd": latd, "note": g.get("note") or g.get("skipped") or g.get("unavailable")})
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


def tier(rows: list, name: str) -> list:
    """The rows restricted to one tier: 'basic' (easy, medium, hard) or 'complex'."""
    ids = {t["id"] for t in code_tasks.TASKS if (t["level"] == "complex") == (name == "complex")}
    return [{**r, "per": {k: v for k, v in r["per"].items() if k in ids},
             "lat": [x for k, x in r["latd"].items() if k in ids]} for r in rows]


def tier_section(md: list, rows: list, name: str, title: str, levels: tuple) -> None:
    ids = [t for t in code_tasks.TASKS if (t["level"] == "complex") == (name == "complex")]
    n = len(ids)
    md += ["", f"## {title}", "",
           f"{n} tasks, {sum(t['n_tests'] for t in ids)} tests. One task is {100 / n:.0f} points of 'solved'.", "",
           "| model | where | solved | tests passed | " + " | ".join(levels) + " | p50 s | p95 s |",
           "|---|---|---|---|" + "---|" * len(levels) + "---|---|"]
    ranked = sorted(rows, key=lambda r: (-summary(r)["rate"], -summary(r)["solved"]))
    ranked = [r for r in ranked if r["per"]]
    for r in ranked:
        s = summary(r)
        cells = [("{}/{}".format(*by(r, "level", l)[:2]) if l != "all" else "") for l in levels]
        md.append(f"| {r['model']} | {'cloud' if r['cloud'] else 'local'} | {pct(s['solved'], s['n'])} | {pct(s['passed'], s['total'])} | "
                  + " | ".join(cells) + " | " + (f"{statistics.median(r['lat']):.1f} | {p(r['lat'], .95):.1f} |" if r["lat"] else "- | - |"))
    short = [r for r in ranked if len(r["per"]) < n]
    if short:
        md.append("\nIncomplete: " + ", ".join(f"{r['model']} ({len(r['per'])}/{n} scored so far)" for r in short))
    full = [r for r in ranked if len(r["per"]) == n]
    if full:
        loc = [r for r in full if not r["cloud"]]
        f0 = summary(full[0])
        md += ["", f"- **Best overall:** {full[0]['model']} ({pct(f0['passed'], f0['total'])} of tests, {f0['solved']}/{n} tasks solved)"]
        if loc:
            l0 = summary(loc[0])
            md.append(f"- **Best local:** {loc[0]['model']} ({pct(l0['passed'], l0['total'])} of tests, {l0['solved']}/{n} tasks solved)")
        tied = [r["model"] for r in full[1:] if summary(r)["solved"] >= f0["solved"] - 1]
        if tied:
            md.append("- Within one task of the best (do not rank these against each other): " + ", ".join(tied))
        half = [r["model"] for r in full if summary(r)["solved"] * 2 >= n]
        md.append(f"- Solved at least half of the tasks: {', '.join(half) if half else 'none'}")


def main(out: Path) -> None:
    rows = load(out)
    notes = json.loads((out / "notes.json").read_text()) if (out / "notes.json").exists() else {"notes": [], "models": []}
    st = json.loads((out / "selftest.json").read_text()) if (out / "selftest.json").exists() else None
    T = code_tasks.TASKS
    nb, nc = sum(t["level"] != "complex" for t in T), sum(t["level"] == "complex" for t in T)
    md = [f"# Coding bench: {out.name}", ""]
    md.append(f"{len(T)} invented Python tasks with hidden pytest tests ({sum(t['n_tests'] for t in T)} tests in all), in two tiers reported separately: "
              f"{nb} basic tasks ({sum(t['level'] == 'easy' for t in T)} easy, {sum(t['level'] == 'medium' for t in T)} medium, "
              f"{sum(t['level'] == 'hard' for t in T)} hard: functions, bug fixes, regexes) and {nc} complex tasks (stateful classes, a parser, "
              "a 40-line spec to implement, algorithms with edge cases, a two-module bug fix merged into one file, a small template engine). "
              "One shot, temperature 0, one fenced Python block extracted in code, no retries (pass@1). Model code ran only in a Docker "
              "sandbox (no network, read-only filesystem, non-root, limited CPU/memory/processes, 10 s). Scoring is done in code. Local models "
              "ran with sensitive=true; cloud models (sensitive=false) saw only these invented public tasks.")
    md.append("")
    md.append("**Reading the numbers:** a single run at temperature 0 is one sample, so differences of one or two tasks are noise. "
              "Test-level pass rate is finer but not independent of the task count.")
    if st and "probes_passed" in st:
        md.append(f"\nSandbox self-test (a known-bad snippet that tries the network, writes outside its tmpfs, runs as root, forks without limit, "
                  f"fills the disk, hangs or eats memory): {st['probes_passed']} probes blocked, infinite loop {st['hang_kind']}, "
                  f"memory hog {st['mem_kind']}, good snippet passes: {st['good_snippet_passes']}.")
    for fn, title in (("HYPOTHESIS.md", "Hypothesis, basic tier (written before the run)"),
                      ("HYPOTHESIS-complex.md", "Hypothesis, complex tier (written before the complex tasks were run)")):
        if (out / fn).exists():
            md += ["", f"## {title}", "", (out / fn).read_text().strip()]
    tier_section(md, tier(rows, "basic"), "basic", "Basic tier (easy / medium / hard)", ("easy", "medium", "hard"))
    tier_section(md, tier(rows, "complex"), "complex", "Complex tier", ("complex",))
    for r in rows:
        if r["note"] and not r["per"]:
            md.append(f"- Not run: {r['model']}: {r['note']}")
        elif r["note"]:
            md.append(f"- {r['model']}: {r['note']}")
    for n in notes["notes"]:
        md.append(f"- Left out: {n}")
    ranked = sorted([r for r in rows if r["per"]], key=lambda r: (-summary(r)["rate"], -summary(r)["solved"]))
    md += ["", "## Basic tier by task type", "", "| model | " + " | ".join(KINDS) + " |", "|---|" + "---|" * len(KINDS)]
    for r in tier(ranked, "basic"):
        md.append(f"| {r['model']} | " + " | ".join(f"{a}/{b} tasks, {pct(c, d)} tests" for a, b, c, d in (by(r, 'kind', k) for k in KINDS)) + " |")
    md += ["", "## Failure kinds (tasks not fully solved)", "", "| model | tier | " + " | ".join(FAILURES) + " |", "|---|---|" + "---|" * len(FAILURES)]
    for r in ranked:
        for tn in ("basic", "complex"):
            per = tier([r], tn)[0]["per"]
            cnt = {f: sum(v["failure"] == f for v in per.values()) for f in FAILURES}
            md.append(f"| {r['model']} | {tn} | " + " | ".join(str(cnt[f] or "") for f in FAILURES) + " |")
    md.append("\n`wrong_answer` = the code ran and some tests failed. `import_error` = the module did not import or lacked the requested name. "
              "`killed` = out of memory or process limit. `not_run` = code waiting for the sandbox.")
    md += ["", "## Per task", "", "Cell = tests passed / total (a full solve is marked ✓).", "",
           "| task | level | " + " | ".join(r["model"] for r in ranked) + " |", "|---|---|" + "---|" * len(ranked)]
    for t in T:
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
