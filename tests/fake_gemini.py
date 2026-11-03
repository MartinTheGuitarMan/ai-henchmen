#!/usr/bin/env python3
"""Stand-in for the gemini binary. Behaviour picked by FAKE_GEMINI_MODE."""
import json, os, subprocess, sys, time
mode = os.environ.get("FAKE_GEMINI_MODE", "ok")
prompt = sys.stdin.read()
if os.environ.get("FAKE_ARGV_OUT"):
    open(os.environ["FAKE_ARGV_OUT"], "w").write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "prompt": prompt}))
if mode == "sleep":
    time.sleep(30)
if mode in ("ok", "commit"):
    with open("calc.py", "a") as f:
        f.write("\ndef sub(a, b):\n    return a - b\n")
    open("new_file.txt", "w").write("hello\n")
    if mode == "commit":
        subprocess.run(["git", "add", "-A"], check=True)
        subprocess.run(["git", "commit", "-qm", "agent commit"], check=True)
    out = {"response": "Added sub().\n<SUMMARY>Added sub to calc.py and new_file.txt.</SUMMARY>",
           "stats": {"models": {"gemini-x": {"tokens": {"total": 10}}}}}
    print(json.dumps(out)); sys.exit(0)
if mode == "solve":
    open("solution.py", "w").write(os.environ["FAKE_SOLUTION"])
    if os.environ.get("FAKE_EXTRA"):
        open(os.environ["FAKE_EXTRA"], "w").write("x\n")
    print(json.dumps({"response": "done <SUMMARY>wrote solution.py</SUMMARY>"})); sys.exit(0)
if mode == "503":
    print('Attempt 1 failed with status 503. {"error": {"code": 503, "message": "This model is currently experiencing high demand.", "status": "UNAVAILABLE"}}', file=sys.stderr)
    sys.exit(1)
if mode == "429":
    print("Error: 429 rate limit exceeded", file=sys.stderr); print(json.dumps({"response": ""})); sys.exit(1)
if mode == "error":
    print("Something broke " + json.dumps({"error": {"code": 500, "message": "boom"}}), file=sys.stderr); sys.exit(1)
if mode == "turns":
    print(json.dumps({"response": "partial"})); sys.exit(53)
if mode == "long":
    print(json.dumps({"response": "x" * 50000 + "<SUMMARY>short</SUMMARY>"})); sys.exit(0)
