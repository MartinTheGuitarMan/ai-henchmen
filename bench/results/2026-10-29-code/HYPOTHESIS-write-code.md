Written on 2026-10-30, before any retry-loop call was made (committed before them). The one-shot results of the 25 tasks
already exist and are the baseline.

**What is tested.** `write_code`, an idea from the minions fit log: a function written from a spec, accepted only if its
tests pass in the sandbox. Here as an eval, not a server tool. Each task's hidden test file is dealt out alternately: the
1st, 3rd, 5th... test function become the **visible** tests, the rest the **held-out** tests (imports and helpers go to
both; the visible tests are part of the hidden set). The model's one-shot answer (attempt 1, the stored bench result, same
prompt, temperature 0) is run against the visible tests. If they all pass the code is accepted. Otherwise the model sees
its own answer and the visible failures (pytest output, no hidden test is ever shown) and answers again, at most 3
attempts in all. The final code is the first accepted one, or the last attempt. It is scored on all hidden tests, and on
the held-out tests alone. Model-written code runs only in the night host's sandbox, in its quiet windows, with the same
limits as the bench.

**Pass criteria, per model, fixed now.**
- A, trust: of the tasks the loop accepts, at least 85% pass every held-out test. (If acceptance means little, a "tests
  passed" stamp must not be believed.)
- B, lift: tasks fully solved on all hidden tests rise by at least 3 tasks (of 25) over the one shot.
- PASS = A and B. NO-NEED = the one shot already solves 23 or more of 25 and A holds (nothing to add). FAIL = anything else.
- Route: PASS means use the model inside the retry loop; NO-NEED means use it one-shot; FAIL means do not rely on the loop
  for that model: send the task to a stronger model, or keep a human check.
- A model with fewer than 25 one-shot results, or one that never ran, gets no verdict ("not run"), never a fail.

**Predictions** (tasks solved on all hidden tests, one shot -> loop, and the verdict):

| model | one shot (so far) | loop | verdict |
|---|---|---|---|
| groq-gptoss20b | 22 | 23 to 25 | NO-NEED or PASS |
| groq-gptoss120b | 20 | 22 to 25 | PASS |
| gemini-flashlite | 21 to 22 | 23 to 25 | NO-NEED |
| air-qwen (qwen3.5:9b) | 14 | 17 to 20 | PASS |
| mistral-ministral8b | 11 | 14 to 17 | PASS |
| mini-gemma4b | 4 | 6 to 9 | FAIL (trust: it will pass the visible half and fail the rest) |
| mini-phi4mini | 6 | 8 to 10 | FAIL (same) |
| models still to run | | | no prediction beyond: small ones fail A |

Beyond the table: I expect the loop to help most on `wrong_answer` tasks where the failure message points at the bug (off
by one, a missed edge case) and least on tasks that need the spec read carefully (the complex INI and template tasks),
where feedback from half the tests cannot teach a missing concept. I expect the trust measure to be the weak point for
every small model, because passing half the tests is weak evidence of passing the other half. The cost is 1 to 2 extra
calls for the tasks that need them, so the loop roughly doubles the time on failing tasks and adds nothing on solved ones.
With 25 tasks one task is 4 points, so a lift of 1 or 2 tasks is noise.
