"""Gemma thinking trial: generate the bench tasks with a chosen Ollama (native chat) variant. Usage: probe.py MODEL ids,comma VARIANT"""
import os, sys, json, time, urllib.request
sys.path.insert(0, '.'); sys.path.insert(0, 'bench')
import code_tasks, code_run
tasks = {t["id"]: t for t in code_tasks.TASKS}
MODEL = sys.argv[1]; ids = sys.argv[2].split(','); variants = sys.argv[3].split(',')
V = {
 "think_off": dict(think=False, temp=0.0, n=6000, sys=code_run.SYSTEM),
 "think_off_t6": dict(think=False, temp=0.6, n=6000, sys=code_run.SYSTEM),
 "think_on_t6": dict(think=True, temp=0.6, n=8000, sys=code_run.SYSTEM),
 "think_on_32k": dict(think=True, temp=0.0, n=32000, sys=code_run.SYSTEM),
 "think_on_brief": dict(think=True, temp=0.0, n=8000, sys=code_run.SYSTEM + " Think very briefly (at most a few sentences), then give the final answer."),
}
for vn in variants:
    v = V[vn]
    for tid in ids:
        t = tasks[tid]
        body = {"model": MODEL, "stream": False, "think": v["think"],
                "messages": [{"role": "system", "content": v["sys"]}, {"role": "user", "content": t["prompt"]}],
                "options": {"temperature": v["temp"], "num_predict": v["n"], "num_ctx": 40960 if v["n"] > 8000 else 24576}}
        t0 = time.time()
        r = json.load(urllib.request.urlopen(urllib.request.Request(os.environ.get("OLLAMA_URL", "http://127.0.0.1:11435") + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=3000))
        m = r["message"]; content = m.get("content") or ""; th = m.get("thinking") or ""
        ext = code_run.extract_code(content, "length" if r.get("done_reason") == "length" else "stop")
        print(json.dumps({"variant": vn, "task": tid, "secs": round(time.time() - t0), "done": r.get("done_reason"), "tokens": r.get("eval_count"),
                          "content_len": len(content), "think_len": len(th), "failure": ext["failure"], "code": ext["code"]}), flush=True)
