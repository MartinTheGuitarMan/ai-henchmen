# oMLX trial (2026-11-08)

Question: can oMLX (MLX inference server for macOS) replace Ollama as the headless engine for nightly benches on the
Air, reading LM Studio's existing MLX files instead of a second download?

Method note: the criteria below were written and committed **before oMLX was installed or run**, then frozen.
Model under test: `gemma-4-12B-it-MLX-4bit` (LM Studio folder) against Ollama `gemma4:12b-mlx`. The 26B is not run.
The bench must be finished and everything stopped well before 21:00, so the Ollama overnight bench is not disturbed.

## Pass criteria (frozen)

| id | criterion | pass when |
|---|---|---|
| C1 | Isolated install | Installed in a dedicated venv or `uv tool` dir; nothing system-wide, no launch-at-login, no login item, no menu bar app left running. Uninstall removes it: no oMLX process, no files left outside the venv except noted caches, which are listed and deleted. |
| C2 | Reads LM Studio files in place | Serves `~/.lmstudio/models/lmstudio-community/gemma-4-12B-it-MLX-4bit` from that folder with no copy of the weights and no write to the LM Studio folder: file list, sizes and mtimes of that tree identical before and after. |
| C3 | OpenAI-compatible API, free port, temporary roster | Answers `/v1/chat/completions` on a free local port (not 1234, 8765, 8800, 11434-11437), reached through the existing `openai-compat` backend via a roster entry in a **temporary copy** of the roster. The live roster file is unchanged (hash before and after). |
| C4 | Speed and memory vs Ollama | One fixed coding prompt, temperature 0, 1500 max tokens, same for both; one model loaded at a time; generation tokens/s and peak memory reported for both. Pass when oMLX is not worse than Ollama by more than 15% on tokens/s and not more than 15% above on peak memory (otherwise "fail", numbers still reported). Peak memory is the highest sum of resident memory (RSS) over the server process tree, polled every 0.5 s, plus the system-wide memory-used delta for context. |
| C5 | Hippo test | An ask about an invented entity (made-up person, product or place) gets a refusal or "unknown", not an invention, on 3 different invented entities. Checked by script (refusal markers present, no invented specifics), not by a model. |
| C6 | Unload and stop | Unload of the model on request (API or CLI) frees its RAM (resident memory of the server drops by at least 70% of the loaded delta), the server stops on request, and after the trial no oMLX process or listening port remains. |
| C7 | Code check catches planted bad output | Going through the adapter path (`minions.backends.complete_ex` and the bench's `extract_code`), a planted empty answer and a planted truncated answer (finish reason `length`) are both rejected/flagged, while a good answer passes. |

Verdict rule: **replace Ollama** needs C1 to C7 all pass. **Use alongside** if C1 to C3 and C6 pass and C4 or C5 or C7 fails
in a way that is fixable or only matters for some jobs. **Not worth it** otherwise.

## Results

(filled in after the run)
