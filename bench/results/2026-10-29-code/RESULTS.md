# Coding bench: 2026-10-29-code

25 invented Python tasks with hidden pytest tests (252 tests in all), in two tiers reported separately: 17 basic tasks (6 easy, 8 medium, 3 hard: functions, bug fixes, regexes) and 8 complex tasks (stateful classes, a parser, a 40-line spec to implement, algorithms with edge cases, a two-module bug fix merged into one file, a small template engine). One shot, temperature 0, one fenced Python block extracted in code, no retries (pass@1). Model code ran only in a Docker sandbox (no network, read-only filesystem, non-root, limited CPU/memory/processes, 10 s). Scoring is done in code. Local models ran with sensitive=true; cloud models (sensitive=false) saw only these invented public tasks.

**Reading the numbers:** a single run at temperature 0 is one sample, so differences of one or two tasks are noise. Test-level pass rate is finer but not independent of the task count.

Sandbox self-test (a known-bad snippet that tries the network, writes outside its tmpfs, runs as root, forks without limit, fills the disk, hangs or eats memory): 12/12 probes blocked, infinite loop timeout, memory hog killed, good snippet passes: True.

## Hypothesis, basic tier (written before the run)

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

## Hypothesis, complex tier (written before the complex tasks were run)

Written on 2026-10-29, after the basic tier had started running and before any model was asked a complex task
(committed before those calls). The brief's guess: only GPT-OSS 120B and a Qwen of 14B size clear half, the 4B models
are near zero. The roster's Qwen is `qwen3.5:9b`.

The 8 complex tasks are: a TTL + LRU cache, a task scheduler, an expression evaluator, an INI dialect given as a 40-line
spec, shortest path with tie rules, two interval algorithms, a two-module inventory bug fix merged into one file, and a
template engine given as a spec. Predictions, tasks fully solved out of 8:

| model | predicted solved |
|---|---|
| groq-gptoss120b | 5 to 7 |
| gemini-flashlite | 3 to 5 |
| groq-gptoss20b | 3 to 5 |
| air-qwen (qwen3.5:9b) | 2 to 5 |
| air-gemma4-26b | 2 to 5 |
| mistral-ministral8b | 1 to 3 |
| the 4B models (mini-gemma4b, mini-gemma4e4b, mini-phi4mini) | 0 to 1 |
| mini-nemotronmini | 0 |

Beyond the guess: I expect the clear half-or-more group to be GPT-OSS 120B alone or with one other model, and the
template engine and the expression evaluator to be the tasks fewest models solve (their hidden tests are many small edge
cases, so a model that gets the main idea right can still fail most). Test-level pass rates should separate models better
than solved counts here: a model that nearly gets the INI parser will fail a few of 22 tests, not all. The two-module
bug fix should be the easiest complex task, since the required behaviour is listed in words. Failure kinds: mostly
`wrong_answer`; small local models may add `truncated` or `no_code_block` on the long specs. With 8 tasks one task is
12.5 points, so only large gaps mean anything.

## Basic tier (easy / medium / hard)

17 tasks, 117 tests. One task is 6 points of 'solved'.

| model | where | solved | tests passed | above the do-nothing stub | easy | medium | hard | p50 s | p95 s |
|---|---|---|---|---|---|---|---|---|---|
| groq-gptoss20b | cloud | 17/17 (100%) | 117/117 (100%) | 113/113 (100%) | 6/6 | 8/8 | 3/3 | 1.6 | 10.9 |
| gemini-flashlite | cloud | 16/17 (94%) | 115/117 (98%) | 111/113 (98%) | 6/6 | 8/8 | 2/3 | 17.7 | 26.3 |
| groq-gptoss120b | cloud | 15/17 (88%) | 115/117 (98%) | 111/113 (98%) | 6/6 | 8/8 | 1/3 | 2.2 | 7.6 |
| air-qwen | local | 12/17 (71%) | 99/117 (85%) | 95/113 (84%) | 6/6 | 4/8 | 2/3 | 11.9 | 40.6 |
| air-qwen14b | local | 9/17 (53%) | 94/117 (80%) | 90/113 (80%) | 5/6 | 2/8 | 2/3 | 11.7 | 25.5 |
| mistral-ministral8b | cloud | 10/17 (59%) | 91/117 (78%) | 87/113 (77%) | 4/6 | 5/8 | 1/3 | 1.5 | 4.4 |
| mini-gemma4b | local | 4/17 (24%) | 82/117 (70%) | 78/113 (69%) | 2/6 | 2/8 | 0/3 | 9.6 | 20.7 |
| air-granite | local | 10/17 (59%) | 79/117 (68%) | 75/113 (66%) | 4/6 | 4/8 | 2/3 | 22.8 | 211.9 |
| mini-phi4mini | local | 6/17 (35%) | 79/117 (68%) | 75/113 (66%) | 4/6 | 2/8 | 0/3 | 5.8 | 13.3 |
| mini-gemma4e4b | local | 2/7 (29%) | 15/53 (28%) | 14/52 (27%) | 1/1 | 1/5 | 0/1 | 97.9 | 154.8 |
| stub-do-nothing | baseline | 0/17 (0%) | 4/117 (3%) | - | 0/6 | 0/8 | 0/3 | 0.0 | 0.0 |
| mini-nemotronmini | local | 0/2 (0%) | 0/16 (0%) | 0/15 (0%) | 0/0 | 0/2 | 0/0 | 14.9 | 18.2 |

Incomplete: mini-gemma4e4b (7/17 scored so far), mini-nemotronmini (2/17 scored so far)

- **Best overall:** groq-gptoss20b (117/117 (100%) of tests, 17/17 tasks solved)
- **Best local:** air-qwen (99/117 (85%) of tests, 12/17 tasks solved)
- Within one task of the best (do not rank these against each other): gemini-flashlite
- Solved at least half of the tasks: groq-gptoss20b, gemini-flashlite, groq-gptoss120b, air-qwen, air-qwen14b, mistral-ministral8b, air-granite

## Complex tier

8 tasks, 135 tests. One task is 12 points of 'solved'.

| model | where | solved | tests passed | above the do-nothing stub | complex | p50 s | p95 s |
|---|---|---|---|---|---|---|---|
| gemini-flashlite | cloud | 5/8 (62%) | 95/135 (70%) | 93/133 (70%) | 5/8 | 18.1 | 24.1 |
| groq-gptoss120b | cloud | 5/8 (62%) | 93/135 (69%) | 91/133 (68%) | 5/8 | 5.9 | 17.1 |
| groq-gptoss20b | cloud | 5/8 (62%) | 58/135 (43%) | 56/133 (42%) | 5/8 | 3.5 | 8.4 |
| air-qwen | local | 2/8 (25%) | 53/135 (39%) | 51/133 (38%) | 2/8 | 48.6 | 193.4 |
| mistral-ministral8b | cloud | 1/8 (12%) | 52/135 (39%) | 50/133 (38%) | 1/8 | 9.1 | 81.3 |
| air-qwen14b | local | 0/8 (0%) | 50/135 (37%) | 48/133 (36%) | 0/8 | 60.0 | 157.7 |
| mini-gemma4b | local | 0/8 (0%) | 24/135 (18%) | 22/133 (17%) | 0/8 | 30.4 | 48.0 |
| mini-phi4mini | local | 0/8 (0%) | 22/135 (16%) | 22/133 (17%) | 0/8 | 18.4 | 50.5 |
| air-granite | local | 1/8 (12%) | 18/135 (13%) | 18/133 (14%) | 1/8 | 143.0 | 246.4 |
| stub-do-nothing | baseline | 0/8 (0%) | 2/135 (1%) | - | 0/8 | 0.0 | 0.0 |

- **Best overall:** gemini-flashlite (95/135 (70%) of tests, 5/8 tasks solved)
- **Best local:** air-qwen (53/135 (39%) of tests, 2/8 tasks solved)
- Within one task of the best (do not rank these against each other): groq-gptoss120b, groq-gptoss20b
- Solved at least half of the tasks: gemini-flashlite, groq-gptoss120b, groq-gptoss20b
- Not run: or-nemotron120b: MINION_BACKEND_ERROR: openai-compat HTTP 404: {"error":{"message":"This model is unavailable for free. The paid version is available now - use this slug instead: nvidia/nemotron-3-super-120b-a12b","co
- stub-do-nothing: baseline: does nothing; not a model
- Left out: air-qwen-judge: same model as air-qwen, not run twice
- Left out: typesafe-jev: decision model, does not write code
- Left out: air-jev-style: decision model, does not write code
- Left out: air-jev-style-2b: decision model, does not write code

## Basic tier by task type

| model | write | fix | regex |
|---|---|---|---|
| gemini-flashlite | 9/10 tasks, 75/77 (97%) tests | 4/4 tasks, 23/23 (100%) tests | 3/3 tasks, 17/17 (100%) tests |
| groq-gptoss120b | 9/10 tasks, 76/77 (99%) tests | 4/4 tasks, 23/23 (100%) tests | 2/3 tasks, 16/17 (94%) tests |
| groq-gptoss20b | 10/10 tasks, 77/77 (100%) tests | 4/4 tasks, 23/23 (100%) tests | 3/3 tasks, 17/17 (100%) tests |
| air-qwen | 8/10 tasks, 75/77 (97%) tests | 3/4 tasks, 16/23 (70%) tests | 1/3 tasks, 8/17 (47%) tests |
| air-qwen14b | 4/10 tasks, 57/77 (74%) tests | 3/4 tasks, 22/23 (96%) tests | 2/3 tasks, 15/17 (88%) tests |
| mistral-ministral8b | 5/10 tasks, 58/77 (75%) tests | 4/4 tasks, 23/23 (100%) tests | 1/3 tasks, 10/17 (59%) tests |
| mini-gemma4b | 2/10 tasks, 50/77 (65%) tests | 1/4 tasks, 19/23 (83%) tests | 1/3 tasks, 13/17 (76%) tests |
| mini-phi4mini | 2/10 tasks, 44/77 (57%) tests | 3/4 tasks, 22/23 (96%) tests | 1/3 tasks, 13/17 (76%) tests |
| air-granite | 5/10 tasks, 49/77 (64%) tests | 4/4 tasks, 23/23 (100%) tests | 1/3 tasks, 7/17 (41%) tests |
| mini-gemma4e4b | 2/7 tasks, 15/53 (28%) tests | 0/0 tasks, - tests | 0/0 tasks, - tests |
| stub-do-nothing | 0/10 tasks, 3/77 (4%) tests | 0/4 tasks, 1/23 (4%) tests | 0/3 tasks, 0/17 (0%) tests |
| mini-nemotronmini | 0/2 tasks, 0/16 (0%) tests | 0/0 tasks, - tests | 0/0 tasks, - tests |

## Failure kinds (tasks not fully solved)

| model | tier | generation_error | no_code_block | truncated | syntax_error | import_error | timeout | killed | wrong_answer | not_run |
|---|---|---|---|---|---|---|---|---|---|---|
| gemini-flashlite | basic |  |  |  |  |  |  |  | 1 |  |
| gemini-flashlite | complex |  |  |  |  |  |  |  | 1 |  |
| groq-gptoss120b | basic |  |  |  |  |  |  |  | 2 |  |
| groq-gptoss120b | complex |  |  |  |  |  |  |  | 2 |  |
| groq-gptoss20b | basic |  |  |  |  |  |  |  |  |  |
| groq-gptoss20b | complex |  |  | 3 |  |  |  |  |  |  |
| air-qwen | basic |  |  |  |  | 1 |  |  | 4 |  |
| air-qwen | complex |  |  | 2 |  |  | 1 |  | 3 |  |
| air-qwen14b | basic |  |  |  |  |  |  |  | 8 |  |
| air-qwen14b | complex |  |  |  |  |  |  |  | 8 |  |
| mistral-ministral8b | basic |  |  |  |  |  |  |  | 7 |  |
| mistral-ministral8b | complex |  |  | 1 |  |  |  |  | 6 |  |
| mini-gemma4b | basic |  |  |  |  |  |  |  | 13 |  |
| mini-gemma4b | complex |  |  |  |  | 1 |  |  | 7 |  |
| mini-phi4mini | basic | 1 |  |  |  |  |  |  | 10 |  |
| mini-phi4mini | complex |  |  |  | 1 | 1 |  |  | 6 |  |
| air-granite | basic | 3 |  |  |  |  |  |  | 4 |  |
| air-granite | complex | 6 |  |  |  |  |  |  | 1 |  |
| mini-gemma4e4b | basic |  |  |  | 1 |  |  |  |  | 4 |
| mini-gemma4e4b | complex |  |  |  |  |  |  |  |  |  |
| stub-do-nothing | basic |  |  |  |  |  |  |  | 17 |  |
| stub-do-nothing | complex |  |  |  |  |  |  |  | 8 |  |
| mini-nemotronmini | basic |  |  |  |  |  |  |  |  | 2 |
| mini-nemotronmini | complex |  |  |  |  |  |  |  |  |  |

`wrong_answer` = the code ran and some tests failed. `import_error` = the module did not import or lacked the requested name. `killed` = out of memory or process limit. `not_run` = code waiting for the sandbox.

## Per task

Cell = tests passed / total (a full solve is marked ✓).

| task | level | gemini-flashlite | groq-gptoss120b | groq-gptoss20b | air-qwen | air-qwen14b | mistral-ministral8b | mini-gemma4b | mini-phi4mini | air-granite | mini-gemma4e4b | stub-do-nothing | mini-nemotronmini |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| merge_intervals | medium | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 7/8 | 6/8 | 7/8 | ✓ | 1/8 | 0/8 not_ |
| parse_duration | medium | ✓ | ✓ | ✓ | ✓ | 2/8 | 3/8 | 3/8 | 2/8 | 0/8 gene | 0/8 synt | 0/8 | 0/8 not_ |
| slugify | easy | ✓ | ✓ | ✓ | ✓ | ✓ | 5/7 | 1/7 | 6/7 | 0/7 gene | ✓ | 0/7 | . |
| business_days | medium | ✓ | ✓ | ✓ | ✓ | 4/7 | ✓ | ✓ | 1/7 | ✓ | 0/7 not_ | 0/7 | . |
| parse_csv_line | medium | ✓ | ✓ | ✓ | 7/8 | 1/8 | 3/8 | 3/8 | 4/8 | 1/8 | 0/8 not_ | 0/8 | . |
| wrap_text | medium | ✓ | ✓ | ✓ | 7/8 | 6/8 | ✓ | ✓ | ✓ | ✓ | 0/8 not_ | 0/8 | . |
| compare_versions | hard | 5/7 | ✓ | ✓ | ✓ | 6/7 | 1/7 | 0/7 | 0/7 gene | ✓ | 0/7 not_ | 0/7 | . |
| toposort | hard | ✓ | 9/10 | ✓ | ✓ | ✓ | ✓ | 9/10 | 4/10 | ✓ | . | 1/10 | . |
| lru_cache | medium | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 7/8 | ✓ | ✓ | . | 0/8 | . |
| flatten_dict | easy | ✓ | ✓ | ✓ | ✓ | 5/6 | 5/6 | 5/6 | 5/6 | 1/6 | . | 1/6 | . |
| fix_median | easy | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | . | 1/6 | . |
| fix_chunked | easy | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 5/6 | ✓ | ✓ | . | 0/6 | . |
| fix_unique_bucket | easy | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 2/4 | ✓ | ✓ | . | 0/4 | . |
| fix_top_words | medium | ✓ | ✓ | ✓ | 0/7 | 6/7 | ✓ | 6/7 | 6/7 | ✓ | . | 0/7 | . |
| re_hex_color | easy | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | . | 0/4 | . |
| re_dates_in_text | medium | ✓ | ✓ | ✓ | 0/8 impo | 6/8 | 2/8 | 5/8 | 5/8 | 0/8 gene | . | 0/8 | . |
| re_ipv4 | hard | ✓ | 4/5 | ✓ | 4/5 | ✓ | 4/5 | 4/5 | 4/5 | 3/5 | . | 0/5 | . |
| cx_ttl_cache | complex | ✓ | ✓ | ✓ | 9/10 | 9/10 | ✓ | 1/10 | 6/10 | 0/10 gene | . | 0/10 | . |
| cx_scheduler | complex | ✓ | ✓ | ✓ | 6/11 time | 9/11 | 5/11 | 4/11 | 3/11 | 0/11 gene | . | 0/11 | . |
| cx_expression | complex | 8/31 | 7/31 | 0/31 trun | 0/31 trun | 2/31 | 5/31 | 2/31 | 1/31 | 0/31 gene | . | 0/31 | . |
| cx_ini_parser | complex | 14/22 ok | 13/22 | 0/22 trun | 4/22 | 9/22 | 4/22 | 0/22 | 8/22 | 0/22 gene | . | 0/22 | . |
| cx_shortest_path | complex | ✓ | ✓ | ✓ | ✓ | 5/14 | 11/14 | 5/14 | 0/14 synt | 0/14 gene | . | 2/14 | . |
| cx_schedule_algos | complex | ✓ | ✓ | ✓ | ✓ | 4/11 | 7/11 | 10/11 | 2/11 | ✓ | . | 0/11 | . |
| cx_inventory_fix | complex | ✓ | ✓ | ✓ | 9/12 | 10/12 | 10/12 | 0/12 impo | 0/12 impo | 7/12 | . | 0/12 | . |
| cx_template | complex | 15/24 ok | 15/24 ok | 0/24 trun | 0/24 trun | 2/24 | 0/24 trun | 2/24 | 2/24 | 0/24 gene | . | 0/24 | . |

## Reading, afterwards

Read on 2026-10-31 against the hypotheses written before the runs. One run at temperature 0 is one sample; one basic task is
about 6 points and one complex task 12.5 points, so gaps of one or two tasks mean nothing.

**What is complete and what is not.** Complete (25 of 25 tasks generated and run): groq-gptoss20b, groq-gptoss120b,
gemini-flashlite, mistral-ministral8b, air-qwen (qwen3.5:9b), air-qwen14b (qwen3:14b), air-granite (granite4.2:8b),
mini-gemma4b, mini-phi4mini, plus the do-nothing stub. **Not complete:** mini-gemma4e4b (7 of 25 generated) and
mini-nemotronmini (2 of 25) got only part of one night window each, so their rows are partial and must not be ranked.
**Not run at all:** air-gemma4-26b and air-gptoss20b (LM Studio, 16 GB and about 12 GB loads: the laptop's memory gate never
opened, and at times it was on battery), and or-nemotron120b (its free slug no longer exists; the paid one was not tried).
Not run is never counted as wrong.

**Basic tier against HYPOTHESIS.md.** In range: groq-gptoss120b (15, predicted 14 to 16), air-qwen (12, 11 to 14),
mistral-ministral8b (10, 8 to 11), mini-phi4mini (6, 5 to 9). Just outside: gemini-flashlite 16 (12 to 15), mini-gemma4b 4
(5 to 9). The big miss is **groq-gptoss20b: 17 of 17, predicted 10 to 14**. The prediction that no model solves all three
hard tasks was wrong (gptoss20b solved them). The 4B models and phi4-mini did fine on easy tasks and failed the hard ones
as predicted.

**Complex tier against HYPOTHESIS-complex.md.** Every model with a full row landed in its predicted range: groq-gptoss120b
5 of 8 (5 to 7), gemini-flashlite 5 (3 to 5), groq-gptoss20b 5 (3 to 5), air-qwen 2 (2 to 5), mistral-ministral8b 1 (1 to 3),
mini-gemma4b and mini-phi4mini 0 (0 to 1). The request's own guess, that only GPT-OSS 120B and a Qwen3 14B clear half and the
4B models are near zero, was half right: the 4B models are at zero, but three cloud models cleared half (gemini-flashlite,
groq-gptoss120b and groq-gptoss20b), and qwen3:14b solved **0 of 8** (37% of tests), no better than the 9B. The guess was
for the best Qwen; the roster's second Qwen is the one tested. air-granite solved 1 of 8; 6 of its 8 complex tasks (and 3 basic ones) hit the
300-second call timeout, which counts as a failed task here (a timeout is a result of speed, not a gap), but it also means
the number reflects its speed on the Air as much as its code. On the complex tier the test-level rate separates models
better than solved counts, as predicted: groq-gptoss120b and gemini-flashlite about 70%, groq-gptoss20b 43%.

**The 6000-token cap (second protocol).** Six pairs ended `truncated` in the main run: groq-gptoss20b 3, air-qwen 2,
mistral-ministral8b 1. They were run again with a 16000-token cap and a longer timeout (folder `cap16k`, one protocol
change only). Result: groq-gptoss20b then answered cx_expression (7 of 31 tests) and cx_template (15 of 24) but not
cx_ini_parser (still truncated, it loops in its reasoning); mistral-ministral8b answered cx_template and passed 2 of 24;
air-qwen was cut off again on both tasks. **No task changed from unsolved to solved**, so the main run's solved counts stand,
and the cap explains truncation only for the first two. The main tables keep the 6000-token result (the registered
protocol); the larger-cap answers are in `cap16k/` and not mixed into them.

**The do-nothing stub.** A stub with the right names and no behaviour passes 4 of the 117 basic tests (the regex tasks
`re_hex_color`, `re_ipv4`, `re_dates_in_text`, which have negative-only checks) and 2 of the 135 complex tests. It solves
no task. The tables have a column "above the do-nothing stub" that subtracts it; it moves no model by more than a few
points, and no ranking changes.

**Gates, and what changed on the way.** The run failed to start the night-host models in the 06:00 window because a queue
was blocked on one model waiting for the memory gate; it was fixed to defer such a model and carry on. Later, inside the
22:00 to 23:00 and 06:00 to 07:00 windows only, the margin of free memory that must remain after loading on the night host
was lowered from 25% to 10% at Martin's request; outside the windows it stays 25%. A night-host model starts no call in the
last 8 minutes of a window and a session lasts at most 20 minutes. A model and a sandbox run never overlap on the night host
(a lock shared by all bench processes). Two models could still not be finished in the windows that were left.

**Sources of error.** qwen3.5:9b stands in for the "Qwen3 14B" of the brief in the main tables, and qwen3:14b was added
later. The basic and complex tasks are invented and small; the held-out/visible split of the retry loop (below) deals
test functions alternately, so for tasks with few test functions the visible half is a large share of the evidence.
