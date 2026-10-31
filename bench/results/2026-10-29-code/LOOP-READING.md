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
