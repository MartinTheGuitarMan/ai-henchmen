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
