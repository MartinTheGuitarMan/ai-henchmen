# Model-fit trial: 2026-10-24

Scored in code against known answers on the invented set in `bench/dataset.py`. Local models were called with sensitive=true, cloud models with sensitive=false (invented text only).
Accuracy counts an error as wrong. Latency is per item, seconds, rate-limit waits excluded. About 30 items per tool: one item is about 3 points.

## grounded

| model | where | accuracy | quote kept | reword traps ok | failures | p50 s | p95 s |
|---|---|---|---|---|---|---|---|
| groq-gptoss20b | cloud | 31/31 (100%) | 22/22 (100%) | 5/5 (100%) | 0 | 0.6 | 4.5 |
| groq-gptoss120b | cloud | 31/31 (100%) | 22/22 (100%) | 5/5 (100%) | 0 | 0.7 | 2.7 |
| gemini-flashlite | cloud | 30/31 (97%) | 22/22 (100%) | 5/5 (100%) | 0 | 1.1 | 5.6 |
| mistral-ministral8b | cloud | 29/31 (94%) | 24/25 (96%) | 5/5 (100%) | 0 | 0.5 | 0.7 |
| mini-phi4mini | local | 22/31 (71%) | 26/30 (87%) | 5/5 (100%) | 0 | 1.8 | 2.9 |
| try-llama31-8b | local | 21/31 (68%) | 28/28 (100%) | 5/5 (100%) | 0 | 1.3 | 2.5 |
| mini-gemma4b | local | 20/31 (65%) | 25/31 (81%) | 3/5 (60%) | 0 | 2.6 | 3.2 |
| try-llama32-3b | local | 15/31 (48%) | 30/31 (97%) | 5/5 (100%) | 0 | 1.4 | 2.5 |
| try-ministral8b | local | 14/31 (45%) | 5/24 (21%) | 3/5 (60%) | 0 | 3.0 | 4.4 |
| mini-nemotronmini | local | 11/31 (35%) | 30/31 (97%) | 5/5 (100%) | 0 | 2.3 | 3.2 |
| try-gemma3-1b | local | 9/31 (29%) | 17/31 (55%) | 2/5 (40%) | 0 | 1.6 | 2.2 |

- **Best:** groq-gptoss20b (31/31 (100%))
- **Best local:** mini-phi4mini (22/31 (71%), p50 1.8s)
- **Cheapest good enough:** groq-gptoss20b (cloud, 31/31 (100%), p50 0.6s)
- **Suggested order:** groq-gptoss20b [cloud, public text only] → groq-gptoss120b [cloud, public text only] → gemini-flashlite [cloud, public text only]
- Failed the safety number: try-ministral8b (quote survival under 80%); try-gemma3-1b (quote survival under 80%)
- Not run: air-qwen: unavailable (MINION_DOWN: ollama backend not reachable at http://127.0.0.1:11436/v1/chat/completions (ConnectError))
- Not run: or-nemotron120b: unavailable (MINION_BACKEND_ERROR: openai-compat HTTP 404: {"error":{"message":"Provider returned error","code":404,"metada)

## same

| model | where | accuracy | evidence kept | failures | p50 s | p95 s |
|---|---|---|---|---|---|---|
| gemini-flashlite | cloud | 25/30 (83%) | 19/19 (100%) | 1 | 3.2 | 10.6 |
| mini-phi4mini | local | 21/30 (70%) | 19/20 (95%) | 1 | 1.4 | 1.6 |
| mistral-ministral8b | cloud | 20/30 (67%) | 20/20 (100%) | 0 | 0.4 | 0.7 |
| groq-gptoss20b | cloud | 20/30 (67%) | 19/19 (100%) | 1 | 0.5 | 4.4 |
| groq-gptoss120b | cloud | 20/30 (67%) | 20/20 (100%) | 0 | 0.7 | 2.7 |
| try-llama31-8b | local | 20/30 (67%) | 25/25 (100%) | 0 | 1.0 | 1.3 |
| mini-gemma4b | local | 19/30 (63%) | 19/21 (90%) | 2 | 1.9 | 2.3 |
| try-ministral8b | local | 19/30 (63%) | 18/20 (90%) | 2 | 2.3 | 3.3 |
| try-llama32-3b | local | 18/30 (60%) | 22/22 (100%) | 0 | 1.0 | 1.2 |
| mini-nemotronmini | local | 18/30 (60%) | 19/21 (90%) | 2 | 1.6 | 1.8 |
| try-gemma3-1b | local | 10/30 (33%) | 0/2 (0%) | 2 | 1.8 | 2.5 |

- **Best:** gemini-flashlite (25/30 (83%))
- **Best local:** mini-phi4mini (21/30 (70%), p50 1.4s)
- **Cheapest good enough:** gemini-flashlite (cloud, 25/30 (83%), p50 3.2s)
- **Suggested order:** gemini-flashlite [cloud, public text only]
- Failed the safety number: try-gemma3-1b (evidence missing in over 10%)
- Not run: air-qwen: unavailable (MINION_DOWN: ollama backend not reachable at http://127.0.0.1:11436/v1/chat/completions (ConnectError))
- Not run: or-nemotron120b: unavailable (MINION_BACKEND_ERROR: openai-compat HTTP 404: {"error":{"message":"Provider returned error","code":404,"metada)

## extract

| model | where | accuracy | fields ok | failures | p50 s | p95 s |
|---|---|---|---|---|---|---|
| try-llama31-8b | local | 30/30 (100%) | 113/113 (100%) | 0 | 1.9 | 2.0 |
| try-ministral8b | local | 30/30 (100%) | 113/113 (100%) | 0 | 5.9 | 7.4 |
| groq-gptoss120b | cloud | 29/30 (97%) | 112/113 (99%) | 0 | 0.7 | 1.9 |
| mistral-ministral8b | cloud | 28/30 (93%) | 111/113 (98%) | 0 | 0.5 | 1.1 |
| groq-gptoss20b | cloud | 27/30 (90%) | 110/113 (97%) | 0 | 0.5 | 3.5 |
| mini-phi4mini | local | 27/30 (90%) | 110/113 (97%) | 0 | 2.4 | 2.9 |
| gemini-flashlite | cloud | 27/30 (90%) | 104/113 (92%) | 2 | 3.2 | 7.0 |
| mini-nemotronmini | local | 26/30 (87%) | 109/113 (96%) | 0 | 2.9 | 3.6 |
| mini-gemma4b | local | 26/30 (87%) | 109/113 (96%) | 0 | 3.4 | 3.8 |
| try-llama32-3b | local | 24/30 (80%) | 106/113 (94%) | 0 | 1.8 | 2.1 |
| try-gemma3-1b | local | 21/30 (70%) | 103/113 (91%) | 0 | 2.0 | 2.2 |

- **Best:** try-llama31-8b (30/30 (100%))
- **Best local:** try-llama31-8b (30/30 (100%), p50 1.9s)
- **Cheapest good enough:** try-llama31-8b (local, 30/30 (100%), p50 1.9s)
- **Suggested order:** try-llama31-8b → try-ministral8b → groq-gptoss120b [cloud, public text only]
- Not run: air-qwen: unavailable (MINION_DOWN: ollama backend not reachable at http://127.0.0.1:11436/v1/chat/completions (ConnectError))
- Not run: or-nemotron120b: unavailable (MINION_BACKEND_ERROR: openai-compat HTTP 404: {"error":{"message":"Provider returned error","code":404,"metada)

## classify_batch (support tickets)

| model | where | accuracy | injection traps ok | bad items ok | failures | p50 s | p95 s |
|---|---|---|---|---|---|---|---|
| typesafe-jev | cloud | 34/34 (100%) | 2/2 (100%) | 2/2 (100%) | 0 | 0.2 | 0.2 |
| groq-gptoss120b | cloud | 34/34 (100%) | 2/2 (100%) | 2/2 (100%) | 0 | 0.6 | 0.7 |
| groq-gptoss20b | cloud | 33/34 (97%) | 1/2 (50%) | 2/2 (100%) | 0 | 0.3 | 0.5 |
| gemini-flashlite | cloud | 33/34 (97%) | 2/2 (100%) | 2/2 (100%) | 0 | 4.7 | 6.1 |
| air-jev-style | local | 32/34 (94%) | 2/2 (100%) | 2/2 (100%) | 0 | 0.2 | 0.2 |
| mistral-ministral8b | cloud | 30/34 (88%) | 2/2 (100%) | 2/2 (100%) | 0 | 0.3 | 1.0 |
| try-ministral8b | local | 30/34 (88%) | 2/2 (100%) | 2/2 (100%) | 0 | 1.3 | 1.4 |
| mini-gemma4b | local | 29/34 (85%) | 1/2 (50%) | 2/2 (100%) | 0 | 1.2 | 1.3 |
| mini-phi4mini | local | 28/34 (82%) | 0/2 (0%) | 2/2 (100%) | 0 | 0.8 | 0.9 |
| try-gemma3-1b | local | 24/34 (71%) | 0/2 (0%) | 2/2 (100%) | 0 | 0.8 | 1.0 |
| try-llama32-3b | local | 23/34 (68%) | 0/2 (0%) | 2/2 (100%) | 0 | 0.5 | 0.6 |
| try-llama31-8b | local | 23/34 (68%) | 0/2 (0%) | 2/2 (100%) | 0 | 0.6 | 0.7 |
| mini-nemotronmini | local | 16/34 (47%) | 0/2 (0%) | 2/2 (100%) | 0 | 0.7 | 0.9 |

- **Best:** typesafe-jev (34/34 (100%))
- **Best local:** air-jev-style (32/34 (94%), p50 0.2s)
- **Cheapest good enough:** typesafe-jev (cloud, 34/34 (100%), p50 0.2s)
- **Suggested order:** typesafe-jev [cloud, public text only] → groq-gptoss120b [cloud, public text only] → groq-gptoss20b [cloud, public text only] → gemini-flashlite [cloud, public text only]
- Not run: air-jev-style-2b: unavailable (MINION_DOWN: systemone backend not reachable at http://127.0.0.1:8766/v1/systemone (ConnectError))
- Not run: air-qwen: unavailable (MINION_DOWN: ollama backend not reachable at http://127.0.0.1:11436/v1/chat/completions (ConnectError))
- Not run: or-nemotron120b: unavailable (MINION_BACKEND_ERROR: openai-compat HTTP 404: {"error":{"message":"Provider returned error","code":404,"metada)

## tag_batch (review tags)

| model | where | accuracy | spurious/item | missed/item | no-tag items ok | bad items ok | failures | p50 s | p95 s |
|---|---|---|---|---|---|---|---|---|---|
| gemini-flashlite | cloud | 28/32 (88%) | 0.10 | 0.07 | 5/6 (83%) | 2/2 (100%) | 1 | 0.8 | 12.5 |
| try-ministral8b | local | 23/32 (72%) | 0.17 | 0.20 | 6/6 (100%) | 2/2 (100%) | 0 | 1.5 | 1.9 |
| try-llama31-8b | local | 21/32 (66%) | 0.20 | 0.23 | 3/6 (50%) | 2/2 (100%) | 0 | 0.6 | 0.9 |
| mini-phi4mini | local | 18/32 (56%) | 0.47 | 0.13 | 4/6 (67%) | 2/2 (100%) | 0 | 0.8 | 1.0 |
| mini-nemotronmini | local | 14/32 (44%) | 0.33 | 0.27 | 0/6 (0%) | 2/2 (100%) | 0 | 0.9 | 1.0 |
| mini-gemma4b | local | 14/32 (44%) | 0.80 | 0.10 | 0/6 (0%) | 2/2 (100%) | 0 | 1.4 | 1.7 |
| try-gemma3-1b | local | 10/32 (31%) | 0.70 | 0.33 | 0/6 (0%) | 2/2 (100%) | 0 | 0.8 | 1.2 |
| try-llama32-3b | local | 9/32 (28%) | 0.97 | 0.27 | 0/6 (0%) | 2/2 (100%) | 0 | 0.7 | 0.7 |

- **Best:** gemini-flashlite (28/32 (88%))
- **Best local:** try-ministral8b (23/32 (72%), p50 1.5s)
- **Cheapest good enough:** gemini-flashlite (cloud, 28/32 (88%), p50 0.8s)
- **Suggested order:** gemini-flashlite [cloud, public text only]
- Failed the safety number: mini-phi4mini (spurious tags over 0.2 per item); mini-nemotronmini (spurious tags over 0.2 per item); mini-gemma4b (spurious tags over 0.2 per item); try-gemma3-1b (spurious tags over 0.2 per item); try-llama32-3b (spurious tags over 0.2 per item)
- Not run: air-qwen: unavailable (MINION_DOWN: ollama backend not reachable at http://127.0.0.1:11436/v1/chat/completions (ConnectError))
- Not run: groq-gptoss120b: unavailable (MINION_BACKEND_ERROR: openai-compat HTTP 400: {"error":{"message":"invalid JSON schema for response_format: 't)
- Not run: groq-gptoss20b: unavailable (MINION_BACKEND_ERROR: openai-compat HTTP 400: {"error":{"message":"invalid JSON schema for response_format: 't)
- Not run: mistral-ministral8b: unavailable (MINION_BACKEND_ERROR: openai-compat HTTP 400: {"object":"error","message":"Invalid structured output syntax",")
- Not run: or-nemotron120b: unavailable (MINION_BACKEND_ERROR: openai-compat HTTP 404: {"error":{"message":"Provider returned error","code":404,"metada)


## Reading the numbers (written by hand from the tables above)

- **Wrong answers from small local models are confident ones.** For `grounded`, the quote check passes almost every
  time (the quote really is in the source), but the quote does not prove the verdict. llama3.1:8b and phi4-mini
  turned 5 and 6 of the 9 unclear claims into contradicted/supported, and llama3.1:8b called 4 of 11 contradicted
  claims supported. The code-side quote check therefore does not protect against these; only the verdict accuracy does.
- **gemma3:4b (the model that answered everything in the smoke test)** is among the weakest: grounded 65%, tag_batch 44%
  with 0.8 spurious tags per item, 0 of 6 no-tag items correct. It is fine for extract (87%) and weak on injection traps.
- **tag_batch cannot run on Groq or Mistral today**: both reject the tag schema (`uniqueItems` / "invalid structured
  output syntax") with HTTP 400. That is a tool/provider issue, not a model score. Not fixed here.
- Not run: `mini-gemma4e4b` (about 8.8 GB; the quiet gate refuses it: free memory would fall below 25 percent on the
  machine that serves it), `air-qwen` (its endpoint was down), `air-jev-style-2b` (server down),
  `or-nemotron120b` (HTTP 404 from the provider, the model id seems gone). Rerun with `bench/run.py` (resumable) when
  they are available.
- Classify here is one model at a time; the live route is a quorum with a judge, so quorum results will differ.

## Proposed routing (not applied; the live roster is unchanged)

| tool | sensitive text (local only) | public text (cloud allowed, after local) |
|---|---|---|
| extract | llama3.1:8b (100%, 1.9 s) → ministral-3:8b (100%, slower) → phi4-mini | groq-gptoss120b → mistral-ministral8b |
| classify / classify_batch | air-jev-style (94%, 0.2 s) → ministral-3:8b (88%); keep the quorum and judge as now | typesafe-jev (100%) → groq-gptoss120b |
| grounded | **no local model is good enough** (best: phi4-mini 71%, llama3.1:8b 68%). If it must stay local, require a judge to confirm every supported/contradicted verdict, or return unclear | groq-gptoss20b (100%) → groq-gptoss120b → gemini-flashlite (97%) |
| same | phi4-mini (70%) is the best local and is weak; treat results as a hint only | gemini-flashlite (83%) |
| tag_batch | ministral-3:8b (72%, 0.17 spurious/item) is the only local model near the bar; use a hint and max_labels=2 | gemini-flashlite (88%) |

Drop from the tag, grounded and same routes: gemma3:4b, gemma3:1b, llama3.2:3b, nemotron-mini.
