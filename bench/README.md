# Model-fit trial

Which model fits which tool? `run.py` sends the same invented, public test set (`dataset.py`, about 30 items per tool
with known answers) to every model in a roster and records raw results; `report.py` turns them into one table per
tool. Scoring is done in code, never by a model.

Tools covered: `grounded` (supported / contradicted / unclear, with reworded-claim traps), `same`, `extract`,
`classify_batch` (includes injection traps and empty items), `tag_batch` (multi-label, no-tag items, empty items).

```bash
uv run python bench/run.py --roster my-roster.json --extra bench/extra-local.example.json \
    --env-file keys.env --out bench/results/RUN          # long: run it detached, it resumes if stopped
uv run python bench/report.py bench/results/RUN > bench/results/RUN/RESULTS.md
```

- Local models are called with `sensitive=true`; cloud models with `sensitive=false` and see only the invented text.
- Before a local model is first used, the quiet-machine gate of `docs/dynamic-models.md` runs (free memory, memory
  pressure, power, hold marker). `--remote PORT=SSHHOST` gates a model that runs on another machine, over ssh.
  A refused model waits (`--max-wait-h`), then is recorded as skipped with the reason.
- Rate limits are waited out and never scored as wrong answers. A provider that rejects a tool's schema outright is
  recorded as `unavailable` with its error.
- With about 30 items per tool, one item is about 3 points: do not read much into small differences.
- Add items to `dataset.py` freely, but keep them invented and unambiguous.
