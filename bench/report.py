"""Turn bench/run.py results into markdown: one table per tool, then best / cheapest good-enough / routing order.

    uv run python bench/report.py bench/results/RUN > bench/results/RUN/RESULTS.md

Everything here is computed from the raw records; nothing is judged by a model.

Rules (fixed in code so the recommendation can be reproduced):
- accuracy = items answered correctly / items in the set (an error counts as wrong).
- best = highest accuracy; ties go to the lower median latency.
- good enough = accuracy within 5 points of the best AND at least 80 percent AND failure rate at most 10 percent AND the
  tool's own safety number is met (grounded: 80 percent of supported/contradicted verdicts keep their quote; same:
  at most 10 percent of different/partly verdicts lack evidence; tag_batch: at most 0.2 spurious tags per item).
- cheapest good-enough = local before cloud, then the lowest median latency.
- routing order = good-enough local models by accuracy then latency, then good-enough cloud models (public text only).
With about 30 items per tool, one item is about 3 points: differences of a few points are noise.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

TITLES = {"grounded": "grounded", "same": "same", "extract": "extract", "classify_batch": "classify_batch (support tickets)",
          "tag_batch": "tag_batch (review tags)"}


def pct(k, n):
    return f"{k}/{n} ({100 * k / n:.0f}%)" if n else "-"


def pctile(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    return s[min(len(s) - 1, max(0, int(len(s) * q + 0.5) - 1))]


def metrics(tool: str, items: list) -> dict:
    n = len(items)
    ok = sum(r["ok"] for r in items)
    errs = [r for r in items if r.get("error") and r.get("expected") is not None and r.get("error") != r.get("got")]
    fails = sum(1 for r in items if r.get("error") and not (r["ok"]))
    lats = [r["latency"] for r in items if r.get("latency")]
    m = {"n": n, "ok": ok, "acc": ok / n if n else 0, "fails": fails, "fail_rate": fails / n if n else 0,
         "p50": statistics.median(lats) if lats else None, "p95": pctile(lats, 0.95), "extra": [], "safe": True, "why": []}
    if tool == "grounded":
        raw = [r for r in items if r.get("raw") in ("supported", "contradicted")]
        surv = sum(1 for r in raw if r["quote_survived"])
        rw = [r for r in items if r["tag"] == "reword"]
        m["extra"] = [pct(surv, len(raw)), pct(sum(r["ok"] for r in rw), len(rw))]
        m["safe"] = not raw or surv / len(raw) >= 0.8
        m["why"] = [] if m["safe"] else ["quote survival under 80%"]
    elif tool == "same":
        ev = [r for r in items if r.get("got") in ("different", "partly") or r.get("evidence_fail")]
        bad = sum(1 for r in ev if r.get("evidence_fail"))
        m["extra"] = [pct(len(ev) - bad, len(ev))]
        m["safe"] = not ev or bad / len(ev) <= 0.1
        m["why"] = [] if m["safe"] else ["evidence missing in over 10%"]
    elif tool == "extract":
        ft = sum(r["fields_total"] for r in items)
        m["extra"] = [pct(sum(r["fields"] for r in items), ft)]
    elif tool == "classify_batch":
        tr = [r for r in items if r["tag"] == "trap"]
        bd = [r for r in items if r["tag"] == "bad"]
        m["extra"] = [pct(sum(r["ok"] for r in tr), len(tr)), pct(sum(r["ok"] for r in bd), len(bd))]
    elif tool == "tag_batch":
        real = [r for r in items if r["tag"] != "bad"]
        bd = [r for r in items if r["tag"] == "bad"]
        sp = sum(r.get("spurious", 0) for r in real)
        ms = sum(r.get("missed", 0) for r in real)
        none = [r for r in real if r["tag"] == "none"]
        m["extra"] = [f"{sp / len(real):.2f}", f"{ms / len(real):.2f}", pct(sum(r["ok"] for r in none), len(none)),
                      pct(sum(r["ok"] for r in bd), len(bd))]
        m["safe"] = sp / len(real) <= 0.2
        m["why"] = [] if m["safe"] else ["spurious tags over 0.2 per item"]
    return m


EXTRA_COLS = {"grounded": ["quote kept", "reword traps ok"], "same": ["evidence kept"], "extract": ["fields ok"],
              "classify_batch": ["injection traps ok", "bad items ok"],
              "tag_batch": ["spurious/item", "missed/item", "no-tag items ok", "bad items ok"]}


def main(run: Path) -> None:
    docs = [json.loads(p.read_text()) for p in sorted(run.glob("*.json"))]
    out = [f"# Model-fit trial: {run.name}", "",
           "Scored in code against known answers on the invented set in `bench/dataset.py`. "
           "Local models were called with sensitive=true, cloud models with sensitive=false (invented text only).",
           "Accuracy counts an error as wrong. Latency is per item, seconds, rate-limit waits excluded. "
           "About 30 items per tool: one item is about 3 points.", ""]
    for tool, title in TITLES.items():
        rows, notes = [], []
        for d in docs:
            u = d["units"].get(tool)
            if not u:
                continue
            if u["status"] != "done":
                notes.append(f"{d['model']}: {u['status']}" + (f" ({u.get('reason', '')[:110]})" if u.get("reason") else ""))
                continue
            rows.append((d, metrics(tool, u["items"])))
        out += [f"## {title}", ""]
        if not rows:
            out += ["No results.", ""] + [f"- {n}" for n in notes] + [""]
            continue
        rows.sort(key=lambda r: (-r[1]["acc"], r[1]["p50"] or 1e9))
        out += ["| model | where | accuracy | " + " | ".join(EXTRA_COLS[tool]) + " | failures | p50 s | p95 s |",
                "|---|---|---|" + "---|" * len(EXTRA_COLS[tool]) + "---|---|---|"]
        for d, m in rows:
            f = lambda v: f"{v:.1f}" if v is not None else "-"
            out.append(f"| {d['model']} | {'cloud' if d['cloud'] else 'local'} | {pct(m['ok'], m['n'])} | "
                       + " | ".join(m["extra"]) + f" | {m['fails']} | {f(m['p50'])} | {f(m['p95'])} |")
        best_acc = rows[0][1]["acc"]
        good = [(d, m) for d, m in rows if m["acc"] >= best_acc - 0.05 and m["acc"] >= 0.8 and m["fail_rate"] <= 0.1 and m["safe"]]
        lat = lambda m: m["p50"] if m["p50"] is not None else 1e9
        out += [""]
        out.append(f"- **Best:** {rows[0][0]['model']} ({pct(rows[0][1]['ok'], rows[0][1]['n'])})")
        local = [(d, m) for d, m in rows if not d["cloud"]]
        if local:
            out.append(f"- **Best local:** {local[0][0]['model']} ({pct(local[0][1]['ok'], local[0][1]['n'])}, p50 {local[0][1]['p50']:.1f}s)")
        if good:
            cheapest = sorted(good, key=lambda r: (r[0]["cloud"], lat(r[1])))[0]
            order = sorted([g for g in good if not g[0]["cloud"]], key=lambda r: (-r[1]["acc"], lat(r[1]))) + \
                    sorted([g for g in good if g[0]["cloud"]], key=lambda r: (-r[1]["acc"], lat(r[1])))
            out.append(f"- **Cheapest good enough:** {cheapest[0]['model']} ({'cloud' if cheapest[0]['cloud'] else 'local'}, "
                       f"{pct(cheapest[1]['ok'], cheapest[1]['n'])}, p50 {cheapest[1]['p50']:.1f}s)")
            out.append("- **Suggested order:** " + " → ".join(d["model"] + (" [cloud, public text only]" if d["cloud"] else "")
                                                             for d, _ in order))
        else:
            out.append("- **Cheapest good enough:** none met the bar (80% accuracy, within 5 points of best, "
                       "failures ≤ 10%, tool safety number). Do not route this tool to a small model on these results.")
        unsafe = [f"{d['model']} ({', '.join(m['why'])})" for d, m in rows if not m["safe"]]
        if unsafe:
            out.append("- Failed the safety number: " + "; ".join(unsafe))
        out += [f"- Not run: {n}" for n in notes]
        out.append("")
    print("\n".join(out))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
