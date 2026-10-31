# write_code retry-loop eval

25 tasks. Attempt 1 is the stored one-shot answer; visible tests drive up to 3 attempts; the final code is scored on all hidden tests and on the held-out half alone. One task is 4 points, so differences of one or two tasks are noise.

| model | one shot (tasks / tests) | loop (tasks / tests) | change | accepted | trust: accepted that pass every held-out test | retried -> fixed | median extra s | verdict |
|---|---|---|---|---|---|---|---|---|
| gemini-flashlite | 21/25 (210/252) | 21/25 (210/252) | +0 | 24/25 | 23/24 (96%) | 1 -> 0 | 4 | **FAIL** (lift +0 below +3) |
| groq-gptoss120b | 20/25 (208/252) | 21/25 (209/252) | +1 | 24/25 | 22/24 (92%) | 2 -> 1 | 6 | **FAIL** (lift +1 below +3) |
| groq-gptoss20b | 22/25 (175/252) | 22/25 (202/252) | +0 | 24/25 | 23/24 (96%) | 3 -> 0 | 3 | **FAIL** (lift +0 below +3) |
| mistral-ministral8b | 11/25 (143/252) | 15/25 (168/252) | +4 | 18/25 | 15/18 (83%) | 13 -> 4 | 10 | **FAIL** (trust 83% below 85%) |

- air-granite: not run yet or incomplete (0/25 tasks looped, 25/25 one-shot results). No verdict.
- air-qwen: not run yet or incomplete (16/25 tasks looped, 25/25 one-shot results). No verdict.
- air-qwen14b: not run yet or incomplete (11/25 tasks looped, 25/25 one-shot results). No verdict.
- mini-gemma4b: not run yet or incomplete (7/25 tasks looped, 25/25 one-shot results). No verdict.
- mini-gemma4e4b: not run yet or incomplete (0/25 tasks looped, 7/25 one-shot results). No verdict.
- mini-nemotronmini: not run yet or incomplete (0/25 tasks looped, 2/25 one-shot results). No verdict.
- mini-phi4mini: not run yet or incomplete (0/25 tasks looped, 25/25 one-shot results). No verdict.
- or-nemotron120b: no one-shot results, so no loop run (MINION_BACKEND_ERROR: openai-compat HTTP 404: {"error":{"message":"This model is unavailable for free. The paid version is available now - use this slug instead: nvidia/nemotron-3-super-120b-a12b","co)
- stub-do-nothing: not run yet or incomplete (0/25 tasks looped, 25/25 one-shot results). No verdict.

## Reading

Verdicts follow the criteria in HYPOTHESIS-write-code.md exactly; they are not softened here.

**What was measured.** Only four models finished all 25 tasks of the retry loop (attempt 1 = the stored one-shot answer; up
to 3 attempts in all; visible tests only for the feedback; scored on all hidden tests and on the held-out half). The others
stopped part-way, because each attempt needs a sandbox run and sandbox runs are only allowed in two one-hour windows, with
no model loaded at the same time on the night host. Finished: gemini-flashlite, groq-gptoss120b, groq-gptoss20b,
mistral-ministral8b. Partly done (no verdict): air-qwen 16 of 25 tasks looped, air-qwen14b 11, mini-gemma4b 7; not started:
mini-phi4mini, air-granite, mini-gemma4e4b, mini-nemotronmini. Not run at all: air-gemma4-26b, air-gptoss20b.

**Verdicts (by the rules as written).**
- **gemini-flashlite, groq-gptoss120b, groq-gptoss20b: FAIL on lift** (+0, +1, +0 tasks). The loop is not worth it for them:
  they already solve 20 to 22 of 25 in one shot, and the feedback fixed 0 of 1, 1 of 2 and 0 of 3 retried tasks. Trust is
  high (96%, 92%, 96% of accepted answers pass every held-out test). In spirit this is "no need", but the NO-NEED rule
  needed a one-shot score of 23 or more and none reached it (21, 20, 22), so by the pre-set rule they FAIL. Route: use them
  one-shot.
- **mistral-ministral8b: FAIL on trust, narrowly** (83%, 15 of 18 accepted answers pass the held-out half, needed 85%) with a
  real lift: +4 tasks (11 to 15), 13 retried and 4 fixed. One accepted answer fewer wrong would have made it a PASS, so treat
  it as borderline, not as a clear no. Route: the loop helps this model, but its "tests passed" stamp is not enough alone;
  add a second check (more tests or a stronger model) before relying on it.

**Against the hypothesis.** The predicted lifts for the strong models (0 to 3) held; the prediction that groq-gptoss120b would
PASS did not (+1). mistral-ministral8b was predicted PASS and landed just under the trust bar. No prediction can be scored for
the air-qwen models and the small local models, which did not finish.

**Lesson for the design.** The loop is limited by the windows, not by the models: for a night-host model one retry round
needs a window for the sandbox and another for the model. A real `write_code` tool would run its sandbox next to the model.
