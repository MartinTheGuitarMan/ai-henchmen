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

Source: oMLX 0.7.3 (Apache 2.0), release wheel `omlx-0.7.3-cp313-cp313-macosx_15_0_universal2.whl` (38.8 MB, sha256
`9b09aa8f...a67d`) from github.com/jundot/omlx/releases/tag/v0.7.3. Not on PyPI; the CLI install path is that wheel, the
Homebrew tap or a source build (the DMG is the menu bar app, not used). Python 3.13 in a dedicated `uv venv`; dependencies from PyPI.
Run on the Air, 2026-11-08, 11:48 to 12:05, with the Air bench paused by the hub for the window (a first attempt next
to the live Ollama bench was refused by oMLX, see C4 note). Raw numbers: `bench/results/2026-11-08-omlx/`.
Helper: `scripts/omlx_trial.py`. Flags used: `omlx serve --model-dir <dir with a symlink to the model> --port 8123
--paged-ssd-cache-dir <scratch> --memory-guard safe --headless`.

| id | result | evidence |
|---|---|---|
| C1 | **pass** | Venv in a scratch dir only. No LaunchAgent, no login item added (login items unchanged), no menu bar app (`--headless`, DMG not installed). Side effect: first run creates `~/.omlx` (settings, logs, a `bin/omlx-cluster-python` shim, `usage.sqlite3`); did not exist before, deleted after. Venv, wheel and caches removed; no `omlx` process or port 8123 left. `uv` cache keeps the downloaded dependency wheels (shared cache, not removed). |
| C2 | **pass** | Served from the LM Studio folder through a symlink (no copy). File list, sizes and mtimes of all of `~/.lmstudio/models/lmstudio-community` identical before and after. Note: `--model-dir` expects model folders directly under it, so LM Studio's `publisher/model` layout needs the parent pointed at, or a symlink dir as here. |
| C3 | **pass** | `/v1/chat/completions` on port 8123, called through the existing `openai-compat` backend (`minions.backends.complete_ex`), no new adapter. Roster entry in a temporary copy (`roster.omlx-temp.json`); live roster hash identical before and after. |
| C4 | **fail** | Same prompt, temp 0, 1500 max tokens, one model loaded at a time (table below). oMLX 15.9 tok/s vs Ollama 34.0 tok/s: 53% slower (limit was 15%). Peak RSS 7.58 GB vs 7.05 GB (+7%, ok). System-wide used-memory delta 7.9 vs 12.1 GB is noisy (other processes on the Air) and only indicative. |
| C5 | **pass** | 3 of 3 invented entities answered "I cannot confirm the existence of ..." with no invented specifics. |
| C6 | **pass** | Needs an API key (`--api-key`, test key) for `POST /admin/api/models/<id>/unload`. Resident memory 7.90 GB loaded, 0.66 GB after unload (91% freed). Server stopped on SIGTERM; nothing left running. Idle server alone: 0.2 GB. |
| C7 | **pass** | Through `complete_ex` + `bench/code_run.extract_code`: a real call with `max_tokens=20` returned finish `length` and was flagged `truncated`; planted empty reply flagged (`no_code_block`; `truncated` if finish is length), planted truncated fence and truncated no-fence flagged `truncated`; a good reply passes. |

Speed and memory, same prompt (invented merge-intervals task):

| engine | completion tokens | tok/s (wall) | tok/s (engine's own) | warm-up load | peak RSS (server tree) | finish |
|---|---|---|---|---|---|---|
| oMLX 0.7.3, gemma-4-12B-it-MLX-4bit (LM Studio files) | 729 | 15.9 | n/a | 6.9 s | 7.58 GB | stop |
| Ollama, gemma4:12b-mlx (NVFP4) | 1210 | 34.0 | 34.1 | 2.9 s | 7.05 GB | stop |

Caveats: the models are different quantizations (4-bit affine vs NVFP4) and each wrote a different-length answer, so
quality is not compared; the 4-bit speed gap may partly be oMLX's generic path for this model family (the wheel is
precompiled; no Xcode custom kernels were built). One run each, no repeats. Not tried: the Homebrew build with
custom kernels, other KV settings.

Also observed: with a live Ollama model resident and swap at 4.9 of 6.1 GB, oMLX's memory guard refused to load the
12B (HTTP 507, "does not fit under the dynamic memory ceiling (4.30GB)"). That is safe behaviour for a shared machine,
but it also means it cannot co-run with Ollama's resident model on the 24 GB Air.

## Verdict: **not worth it** (as the nightly engine on the Air)

TLDR: oMLX serves LM Studio's MLX files in place with no copy and passes every check except speed, but it generated at
under half Ollama's rate (15.9 vs 34.0 tok/s) on the same prompt, so it should not replace Ollama.

Reason: C1 to C3 and C5 to C7 pass, which is what the second-download question was about; C4 fails by a wide
margin, and a nightly bench is throughput-bound. Revisit only if a build with the custom kernels (or a newer
version) closes the speed gap in a repeat run; the saving would be about 7 GB of disk for one model, not RAM.

## Uninstall confirmation

Venv, release wheel, SSD cache dir, symlink dir and `~/.omlx` deleted; no oMLX process, no listener on 8123, no login
item or LaunchAgent; Ollama's 12B unloaded (`keep_alive 0`) and the Air bench handed back to the hub. Remaining: the
shared `uv` download cache.
