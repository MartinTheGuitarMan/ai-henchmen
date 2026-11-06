# Model-fit trial: 2026-11-05-jev

Scored in code against known answers on the invented set in `bench/dataset.py`. Local models were called with sensitive=true, cloud models with sensitive=false (invented text only).
Accuracy counts an error as wrong. Latency is per item, seconds, rate-limit waits excluded. About 30 items per tool: one item is about 3 points.

## grounded

No results.


## same

No results.


## extract

No results.


## classify_batch (support tickets)

| model | where | accuracy | injection traps ok | bad items ok | failures | p50 s | p95 s |
|---|---|---|---|---|---|---|---|
| air-jev-style | local | 32/34 (94%) | 2/2 (100%) | 2/2 (100%) | 0 | 0.0 | 0.1 |

- **Best:** air-jev-style (32/34 (94%))
- **Best local:** air-jev-style (32/34 (94%), p50 0.0s)
- **Cheapest good enough:** air-jev-style (local, 32/34 (94%), p50 0.0s)
- **Suggested order:** air-jev-style
- Not run: air-jev-style-qwen35-2b: unavailable (MINION_DOWN: systemone backend not reachable at http://127.0.0.1:8766/v1/systemone (ConnectError))

## tag_batch (review tags)

No results.


## ask (made-up animals, papers, places vs real controls)

No results.


