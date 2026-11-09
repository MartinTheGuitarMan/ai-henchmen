"""Speculative-decoding A/B: tokens/s and answer hash per option set. Usage: spec.py MODEL ids '{"name":{opts}}'"""
import os, sys, json, urllib.request, hashlib
sys.path.insert(0, '.'); sys.path.insert(0, 'bench')
import code_tasks, code_run
tasks = {t["id"]: t for t in code_tasks.TASKS}
MODEL = sys.argv[1]; ids = sys.argv[2].split(','); variants = json.loads(sys.argv[3])
for name, opts in variants.items():
    for tid in ids:
        body = {"model": MODEL, "stream": False, "think": False, "messages": [{"role": "system", "content": code_run.SYSTEM}, {"role": "user", "content": tasks[tid]["prompt"]}],
                "options": {"temperature": 0, "num_predict": 1500, "num_ctx": 24576, "seed": 1, **opts}}
        r = json.load(urllib.request.urlopen(urllib.request.Request(os.environ.get("OLLAMA_URL", "http://127.0.0.1:11435") + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=900))
        c = r["message"]["content"]
        print(json.dumps({"v": name, "task": tid, "tok": r["eval_count"], "tps": round(r["eval_count"] / (r["eval_duration"] / 1e9), 1), "sha": hashlib.sha1(c.encode()).hexdigest()[:8]}), flush=True)
