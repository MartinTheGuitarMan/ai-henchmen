"""Turn a paired comparison of two result sets into journal table lines. Plain code, no model.

    uv run python scripts/compare_digest.py OLD NEW [--tool T] [--model M] [--label "claims fix"]

OLD and NEW are what `trial_compare.py diff` takes (a .jsonl file, or a folder of them). The numbers come from
`trial_compare.per_case` / `compare`; this adds what its table lacks: the rates in percent, the change in percentage points, the
counts of better and worse cases, and the worse cases by name. One line per tool and model, ready to paste into a journal.
A pair with no scored answer on one side shows `-` (no rate, no change)."""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trial_compare as tc  # noqa: E402


def load(path: str) -> list[dict]:
    """trial_compare.load, but an empty side or a missing file stops with a message instead of giving an empty table."""
    if not Path(path).expanduser().exists():
        raise SystemExit(f"{path}: not found")
    recs = tc.load(path)
    if not recs:
        raise SystemExit(f"{path}: no records")
    return recs


def digest(old: dict, new: dict) -> list[dict]:
    res = tc.compare(old, new)
    rows: dict = defaultdict(lambda: {"better": 0, "worse": 0, "only_old": 0, "only_new": 0, "worse_cases": []})
    for r in res["rows"]:
        tool, model, case = r["key"]
        d = rows[(tool, model)]
        if r["verdict"] in d:
            d[r["verdict"]] += 1
        if r["verdict"] == "worse":
            d["worse_cases"].append(case)
    out = []
    for (tool, model), t in sorted(res["totals"].items()):
        d = rows[(tool, model)]
        ro = round(100 * t["old_ok"] / t["old_n"]) if t["old_n"] else None
        rn = round(100 * t["new_ok"] / t["new_n"]) if t["new_n"] else None
        delta = None if ro is None or rn is None else round(100 * t["new_ok"] / t["new_n"] - 100 * t["old_ok"] / t["old_n"], 1)
        out.append({"tool": tool, "model": model, **t, "old_pct": ro, "new_pct": rn, "delta": delta, **d})
    return out


def render(rows: list[dict], label: str = "") -> str:
    lines = [f"| {label or 'comparison'}: tool | model | old | new | change | better | worse | worse cases |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        old = f"{r['old_ok']}/{r['old_n']} ({r['old_pct']}%)" if r["old_n"] else "-"
        new = f"{r['new_ok']}/{r['new_n']} ({r['new_pct']}%)" if r["new_n"] else "-"
        delta = "-" if r["delta"] is None else f"{r['delta']:+.1f} pts"
        worse = ", ".join(r["worse_cases"]) or "-"
        lines.append(f"| {r['tool']} | {r['model']} | {old} | {new} | {delta} | {r['better']} | {r['worse']} | {worse} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--tool")
    ap.add_argument("--model")
    ap.add_argument("--label", default="")
    a = ap.parse_args(argv)
    old = tc.per_case(load(a.old), a.model, a.tool)
    new = tc.per_case(load(a.new), a.model, a.tool)
    print(render(digest(old, new), a.label))
    return 0


if __name__ == "__main__":
    sys.exit(main())
