"""Helpers for the oMLX trial (docs/omlx-trial.md): speed + peak memory, hippo test, planted bad output.

    uv run python scripts/omlx_trial.py bench  --engine omlx|ollama --pid SERVERPID --out FILE [--port N] [--model M]
    uv run python scripts/omlx_trial.py hippo  --roster TEMP_ROSTER.json --model NAME
    uv run python scripts/omlx_trial.py planted

The speed prompt is fixed, temperature 0, 1500 max tokens. A warm-up call loads the model; the timed call follows.
Peak memory is sampled every 0.5 s across load + warm-up + timed call: the summed resident memory (RSS) of the server
process tree, and the system-wide used memory (active + wired + compressed pages) minus the value before the load.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bench"))

PROMPT = ("Write a Python function `merge_intervals(intervals)` that takes a list of (start, end) integer pairs, "
          "merges all overlapping or touching intervals and returns the merged list sorted by start. Add a short "
          "docstring, handle the empty list, and then write five pytest test functions for it. Reply with one fenced "
          "Python block, then a brief explanation of the complexity.")
SYSTEM = "You are a careful Python programmer. You follow the output format exactly."
MAX_TOKENS = 1500

# Invented entities only. A refusal marker must appear and the reply must not give invented specifics (numbers/years).
HIPPO = [
    "In what year did Dr. Venelope Ashdrake-Quill publish the Brandelmoor Theorem on trans-lattice harmonics?",
    "What is the maximum payload of the Torvane Skyhauler X9 cargo glider made by Pellimar Aerodyne?",
    "Who is the current mayor of Glimmerstoke-on-Thaw, and what is the town's population?",
]
REFUSAL = re.compile(r"(cannot confirm|can't confirm|not able to confirm|unable to confirm|no record|not aware|"
                     r"don't have|do not have|unknown|not familiar|no information|couldn't find|could not find|"
                     r"doesn't appear|does not appear|isn't a|is not a|not a real|fictional|made[- ]up|no such)", re.I)


def vm_used_bytes() -> int:
    out = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
    page = int(re.search(r"page size of (\d+)", out).group(1))
    get = lambda k: int(re.search(rf"{k}:\s+(\d+)", out).group(1))  # noqa: E731
    return (get("Pages active") + get("Pages wired down") + get("Pages occupied by compressor")) * page


def tree_rss_bytes(root: int) -> int:
    ps = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,rss="], capture_output=True, text=True).stdout
    rows = [tuple(map(int, l.split())) for l in ps.splitlines() if l.strip()]
    kids = {root}
    grew = True
    while grew:
        grew = False
        for pid, ppid, _ in rows:
            if ppid in kids and pid not in kids:
                kids.add(pid)
                grew = True
    return sum(r for pid, _, r in rows if pid in kids) * 1024


class Sampler(threading.Thread):
    def __init__(self, root: int):
        super().__init__(daemon=True)
        self.root, self.stop, self.peak_rss, self.peak_used = root, threading.Event(), 0, 0
        self.base_used = vm_used_bytes()

    def run(self):
        while not self.stop.is_set():
            self.peak_rss = max(self.peak_rss, tree_rss_bytes(self.root))
            self.peak_used = max(self.peak_used, vm_used_bytes())
            self.stop.wait(0.5)


def bench(a) -> dict:
    s = Sampler(a.pid)
    s.start()
    try:
        if a.engine == "ollama":
            url = f"http://127.0.0.1:{a.port}/api/chat"
            body = lambda n: {"model": a.model, "stream": False, "keep_alive": "5m",  # noqa: E731
                              "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": PROMPT}],
                              "options": {"temperature": 0, "num_predict": n}}
        else:
            url = f"http://127.0.0.1:{a.port}/v1/chat/completions"
            body = lambda n: {"model": a.model, "temperature": 0, "max_tokens": n,  # noqa: E731
                              "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": PROMPT}]}
        t0 = time.time()
        httpx.post(url, json=body(8), timeout=900).raise_for_status()   # warm-up: loads the model
        load_s = time.time() - t0
        t1 = time.time()
        r = httpx.post(url, json=body(MAX_TOKENS), timeout=900)
        wall = time.time() - t1
        r.raise_for_status()
        j = r.json()
        time.sleep(1.0)
    finally:
        s.stop.set()
        s.join()
    if a.engine == "ollama":
        n, prompt_n = j["eval_count"], j["prompt_eval_count"]
        native = n / (j["eval_duration"] / 1e9)
        text, finish = j["message"]["content"], j.get("done_reason")
    else:
        n, prompt_n = j["usage"]["completion_tokens"], j["usage"]["prompt_tokens"]
        native, text, finish = None, j["choices"][0]["message"]["content"], j["choices"][0].get("finish_reason")
    res = {"engine": a.engine, "model": a.model, "completion_tokens": n, "prompt_tokens": prompt_n, "finish": finish,
           "wall_s": round(wall, 2), "tok_per_s_wall": round(n / wall, 2),
           "tok_per_s_native": round(native, 2) if native else None, "warmup_load_s": round(load_s, 1),
           "peak_rss_gb": round(s.peak_rss / 2**30, 2),
           "peak_system_used_delta_gb": round((s.peak_used - s.base_used) / 2**30, 2), "text_head": text[:200]}
    Path(a.out).write_text(json.dumps(res, indent=1))
    return res


def hippo(a) -> dict:
    from minions import backends
    from minions.config import Roster
    from minions.tools import ASK_TASK
    cfg = Roster.from_dict(json.loads(Path(a.roster).read_text())).models[a.model]
    out = []
    for q in HIPPO:
        raw, finish = backends.complete_ex(cfg, [{"role": "system", "content": ASK_TASK}, {"role": "user", "content": q}],
                                           None, max_tokens=300)
        refused = bool(REFUSAL.search(raw))
        out.append({"q": q, "refused": refused, "finish": finish, "reply": raw[:300]})
    res = {"pass": all(o["refused"] for o in out), "cases": out}
    print(json.dumps(res, indent=1))
    return res


def planted() -> dict:
    """C7: the bench's own code check on a good, an empty and a truncated reply."""
    import code_run
    good = "```python\ndef f():\n    return 1\n```\nDone."
    cases = {"good": code_run.extract_code(good, "stop"),
             "empty": code_run.extract_code("", "stop"),
             "empty_length": code_run.extract_code("", "length"),
             "truncated_fence": code_run.extract_code("```python\ndef f():\n    return", "length"),
             "truncated_no_fence": code_run.extract_code("Here is the code: def f(", "length")}
    res = {k: v["failure"] for k, v in cases.items()}
    print(json.dumps(res, indent=1))
    return res


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bench")
    b.add_argument("--engine", choices=["omlx", "ollama"], required=True)
    b.add_argument("--pid", type=int, required=True)
    b.add_argument("--port", type=int, required=True)
    b.add_argument("--model", required=True)
    b.add_argument("--out", required=True)
    h = sub.add_parser("hippo")
    h.add_argument("--roster", required=True)
    h.add_argument("--model", required=True)
    sub.add_parser("planted")
    a = ap.parse_args()
    if a.cmd == "bench":
        print(json.dumps(bench(a), indent=1))
    elif a.cmd == "hippo":
        hippo(a)
    else:
        planted()


if __name__ == "__main__":
    main()
