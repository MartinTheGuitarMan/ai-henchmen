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
