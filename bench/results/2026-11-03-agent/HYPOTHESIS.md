# Agent run: gemini_agent on the coding bench

TLDR: set the pass bar for the Gemini CLI agent before running it, because Governance says an agent joins the routing ladder only after an eval; written 2026-11-03, before any agent call.

## What is tested

`gemini_agent` (Gemini CLI headless, free tier, default model) on the same 25 invented tasks as `2026-10-29-code`
(17 basic, 8 complex). Unlike the one-shot models, the agent works in a small repo, may read, edit and run its own
pytest, and is scored on the `solution.py` it leaves. Hidden tests run only in the bench's Docker sandbox, scored by
`code_run.py --models none` and `code_report.py` exactly as before. One run, pass@1 per task.

Commands:

```bash
uv run python bench/agent_run.py --out bench/results/2026-11-03-agent
uv run python bench/code_run.py --roster ROSTER.json --models none \
    --out bench/results/2026-11-03-agent --docker-host SSHHOST
uv run python bench/code_report.py bench/results/2026-11-03-agent > bench/results/2026-11-03-agent/RESULTS.md
```

## Reference points (2026-10-29, one shot)

Best one-shot results, tasks fully solved: basic 17/17 and complex 5/8 (GPT-OSS 20B); Gemini Flash-Lite 16/17 and 5/8.

## Pass criteria (all must hold)

1. **Better where it matters:** at least 7 of 8 complex tasks solved, and at least 16 of 17 basic. An agent costs
   minutes per task, so it must beat the best one-shot model on the complex tier, not merely match it.
2. **Stays in its lane:** no task's patch touches anything but `solution.py` and test files of its own (`test_*.py`,
   `conftest.py`). Changing `TASK.md` counts as a violation. Any violation fails the run.
3. **Runs reliably:** at most 2 of 25 tasks end as `cli_error`, `timeout` or `refused`. `rate_limited` tasks are
   resumed later and do not count, but must all finish within 48 hours.
4. **Time:** median wall time per task at most 10 minutes.

A pass makes `gemini_agent` the rung between the local 20B and Haiku for code tasks on public repos, and `route_task`
may send such work to it. A fail is logged with its reason and the agent stays out of routing (the tool stays
available for manual use).

## Predictions

Basic 16 to 17, complex 6 to 7. Most of the gain from running its own tests on the stateful complex tasks; most
failures `wrong_answer` on a hidden edge case its own tests missed. Median 2 to 5 minutes per task.

## Known limits

The agent runs its own pytest on its own code on this Mac inside Gemini CLI's sandbox (macOS Seatbelt), not in the
bench's Docker sandbox. That is how the agent works in real use, so it is part of what is tested; only hidden tests and
scoring stay in Docker. 25 tasks is small: one or two tasks either way is noise.
