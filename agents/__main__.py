"""Command line: henchmen-agent gemini --repo PATH [--role R] [--base-ref REF] [--test CMD] "task"."""

from __future__ import annotations

import argparse
import json
import sys

from .gemini_cli import run_task


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="henchmen-agent")
    sub = ap.add_subparsers(dest="agent", required=True)
    g = sub.add_parser("gemini", help="run Gemini CLI as an agent in a throwaway clone")
    g.add_argument("task")
    g.add_argument("--repo", required=True)
    g.add_argument("--role", default="default")
    g.add_argument("--base-ref", default="HEAD")
    g.add_argument("--test", dest="test_command")
    args = ap.parse_args(argv)
    result = run_task(args.task, args.repo, role=args.role, base_ref=args.base_ref, test_command=args.test_command)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
