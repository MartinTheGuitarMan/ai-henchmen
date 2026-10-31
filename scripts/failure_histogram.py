"""Rank the failure codes in JSONL run logs into a table. Plain code, no model.

    uv run python scripts/failure_histogram.py results/            # a folder of .jsonl files, or files
    uv run python scripts/failure_histogram.py a.jsonl b.jsonl [--tool score] [--model air-qwen]

Reads the records the trial runners write (`status`, `code`, optionally `tool`, `model`, `case`). A record counts as a failure when
its status is `check_failed`; the code is its `code` (`-` if missing). Records with another status are summarised in one line below
the table (`not_run` is never counted as a failure or as an answer). Order: count down, then code. A line that is not JSON, or a
record without a `status`, stops the run with the file and line number."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def load(paths: list[str]) -> list[dict]:
    files: list[Path] = []
    for p in paths:
        q = Path(p).expanduser()
        found = sorted(q.glob("*.jsonl")) if q.is_dir() else [q]
        if not found:
            raise SystemExit(f"{p}: no .jsonl files")
        files += found
    recs = []
    for f in files:
        if not f.is_file():
            raise SystemExit(f"{f}: not a file")
        for n, raw in enumerate(f.read_text().splitlines(), 1):
            if not raw.strip():
                continue
            try:
                r = json.loads(raw)
            except json.JSONDecodeError as e:
                raise SystemExit(f"{f}: line {n} is not JSON: {e}")
            if not isinstance(r, dict) or "status" not in r:
                raise SystemExit(f"{f}: line {n} has no status")
            recs.append(r)
    if not recs:
        raise SystemExit("no records")
    return recs


def histogram(recs: list[dict], tool: str | None = None, model: str | None = None) -> dict:
    keep = [r for r in recs if (not tool or r.get("tool") == tool) and (not model or r.get("model") == model)]
    fails = [r for r in keep if r["status"] == "check_failed"]
    codes: dict = defaultdict(lambda: {"n": 0, "who": Counter()})
    for r in fails:
        c = codes[r.get("code") or "-"]
        c["n"] += 1
        c["who"][r.get("model") or "?"] += 1
    rows = sorted(((code, d["n"], d["who"]) for code, d in codes.items()), key=lambda t: (-t[1], t[0]))
    other = Counter(r["status"] for r in keep if r["status"] != "check_failed")
    return {"rows": rows, "failures": len(fails), "records": len(keep), "other": dict(other)}


def render(h: dict) -> str:
    lines = ["| rank | code | count | share | models |", "|---|---|---|---|---|"]
    for i, (code, n, who) in enumerate(h["rows"], 1):
        share = round(100 * n / h["failures"])
        lines.append(f"| {i} | {code} | {n} | {share}% | " + ", ".join(f"{m} {k}" for m, k in sorted(who.items())) + " |")
    if not h["rows"]:
        lines.append("| - | no failures | 0 | - | - |")
    other = ", ".join(f"{k} {v}" for k, v in sorted(h["other"].items())) or "none"
    lines.append("")
    lines.append(f"{h['failures']} failures in {h['records']} records; other statuses: {other}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--tool")
    ap.add_argument("--model")
    a = ap.parse_args(argv)
    print(render(histogram(load(a.paths), a.tool, a.model)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
