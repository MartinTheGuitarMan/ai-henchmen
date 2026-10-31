"""The do-nothing baseline: for every task, a stub with the right names and no behaviour. It is run in the sandbox like any
model, so the report can show what the tests award for free (negative-only checks, for example) and subtract it.

    uv run python bench/code_stub.py bench/results/RUN      # writes gen/stub-do-nothing.json; code_run.py runs it in its window
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import code_tasks  # noqa: E402

NAME = "stub-do-nothing"


def stub_for(reference: str) -> str:
    """Same top-level names as the reference solution: functions accept anything and return None, classes are empty,
    plain assignments become None."""
    lines = []
    for n in ast.parse(reference).body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines.append(f"def {n.name}(*args, **kwargs):\n    return None")
        elif isinstance(n, ast.ClassDef):
            lines.append(f"class {n.name}:\n    def __init__(self, *args, **kwargs):\n        pass")
        elif isinstance(n, ast.Assign):
            lines += [f"{t.id} = None" for t in n.targets if isinstance(t, ast.Name)]
    return "\n\n".join(lines) + "\n"


def main(out: Path) -> None:
    (out / "gen").mkdir(parents=True, exist_ok=True)
    tasks = {t["id"]: {"code": stub_for(t["reference"]), "failure": None, "blocks": 1, "detail": "", "latency": 0.0, "finish": "stop", "raw": ""}
             for t in code_tasks.TASKS}
    (out / "gen" / f"{NAME}.json").write_text(json.dumps({"model": NAME, "backend_model": "stub", "cloud": False, "machine": "baseline",
                                                          "note": "baseline: does nothing; not a model", "tasks": tasks}, indent=1))
    print(f"wrote {len(tasks)} stubs")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
