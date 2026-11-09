"""Run probe output through the Docker sandbox on the Mini. Usage: grade.py file.jsonl"""
import sys, json
sys.path.insert(0, '.'); sys.path.insert(0, 'bench')
import code_tasks, sandbox
tasks = {t["id"]: t for t in code_tasks.TASKS}
sb = sandbox.Sandbox("mini")
sb.check()   # fail loudly: a dead Docker must never be graded as wrong answers
rows = [json.loads(l) for l in open(sys.argv[1])]
sb.stage({r["task"]: tasks[r["task"]]["tests"] for r in rows})
for r in rows:
    if r["code"]:
        res = sb.run(r["task"], r["code"]); r["tests"] = f'{res["kind"]} {res["passed"]}/{tasks[r["task"]]["n_tests"]}'
    else:
        r["tests"] = "no code"
    print(r["variant"], r["task"], r["secs"], "s", r["tokens"], "tok", r["done"], "->", r["tests"], flush=True)
