Written on 2026-10-29 before any model was called; committed before the run started.

The owner's expectation: the Qwen model and the 120B GPT-OSS best, the 26B Gemma close behind, and the 4B models only
good on easy tasks. The roster has no Qwen3 14B; its Qwen entry is `qwen3.5:9b`, so that is the one tested and the
comparison is only loosely "Qwen". Predictions in tasks fully solved out of 17 (pass@1, one shot):

| model | predicted solved |
|---|---|
| groq-gptoss120b | 14 to 16 |
| or-nemotron120b (free tier, 120B MoE) | 12 to 15 |
| gemini-flashlite | 12 to 15 |
| air-qwen (qwen3.5:9b) | 11 to 14 |
| air-gemma4-26b | 11 to 14 |
| groq-gptoss20b | 10 to 14 |
| mistral-ministral8b | 8 to 11 |
| mini-gemma4e4b, mini-gemma4b (gemma3:4b), mini-phi4mini | 5 to 9, mostly easy tasks, almost none of the 3 hard ones |
| mini-nemotronmini | 2 to 6 |

Other predictions: no model solves all three hard tasks (version comparison, topological sort, IPv4 regex); the regex
tasks are the most discriminating (small models write patterns that look right and fail edge cases); the bug fixes are
the easiest group; most failures are `wrong_answer` (code that runs and misses an edge case) rather than format failures,
except thinking models, which may run out of tokens (`truncated`). With 17 tasks, differences of one or two tasks are
not meaningful, and I expect the order inside the 9B to 26B group to be unreliable.
