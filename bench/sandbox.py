"""The only place where model-written code is ever run: inside a locked-down Docker container.

Model code is untrusted. This module never runs it any other way, and if Docker cannot be reached it says so and the
caller stops (there is no fallback to the host). Each run is one throwaway container:

  - no network (`--network none`), read-only root filesystem, a 16 MB tmpfs for the one solution file, non-root user,
    all capabilities dropped, no new privileges, 1 CPU, 256 MB memory (no swap), 64 processes, small file/descriptor caps
  - the only host mount is a read-only copy of that task's test file; the solution arrives on stdin
  - 10 seconds for the test run (`timeout` inside the container), and a longer watchdog outside that removes the
    container by name

Docker may be local or on another machine reached with `ssh HOST` (`docker_host`; the night host in this repo's setup).
With a remote host the test files are copied there first, into a cache directory, and mounted from it read-only.

    uv run python bench/sandbox.py selftest [--docker-host SSHHOST]     # known-bad snippet must be blocked
    uv run python bench/sandbox.py build-image [--docker-host SSHHOST]  # python:3.12-slim + pytest (needs network once)
"""
from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

IMAGE = "minions-codebench:1"
BASE_IMAGE = "python:3.12-slim"
PYTEST_VERSION = "8.3.5"
RUN_TIMEOUT_S = 10
WATCHDOG_S = 45
REMOTE_PATH = "export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH; "
REMOTE_TESTS_DIR = ".cache/minions-codebench/tests"      # relative to the docker host user's home
CONTAINER_SCRIPT = ("cat > /work/solution.py && cd /work && "
                    f"exec timeout -k 1 {RUN_TIMEOUT_S} python -u -m pytest -v --tb=no -p no:cacheprovider /tests/test_task.py")


class SandboxUnavailable(RuntimeError):
    """Docker could not be reached. The caller must stop; nothing may run on the host instead."""


def safe_id(name: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", name):
        raise ValueError(f"unsafe task id {name!r}")
    return name


def run_args(name: str, test_path: str, image: str = IMAGE) -> list[str]:
    """The docker command (without the docker prefix) for one run. Constants plus two checked values."""
    return ["run", "--rm", "-i", "--name", name,
            "--network", "none", "--read-only",
            "--tmpfs", "/work:rw,noexec,nosuid,size=16m,mode=1777", "--tmpfs", "/tmp:rw,noexec,nosuid,size=8m,mode=1777",
            "--user", "65534:65534", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--cpus", "1", "--memory", "256m", "--memory-swap", "256m", "--pids-limit", "64",
            "--ulimit", "nofile=256", "--ulimit", "fsize=16777216",
            "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "PYTHONUTF8=1", "-e", "HOME=/work", "-e", "PYTHONPATH=/work",
            "-v", f"{test_path}:/tests/test_task.py:ro",
            image, "sh", "-c", CONTAINER_SCRIPT]


PYTEST_LINE = re.compile(r"^(?:\.\./tests|/tests)/test_task\.py::(\w+) (PASSED|FAILED|ERROR)", re.M)


def parse_pytest(out: str) -> dict:
    """Passed/failed counts from `pytest -v` output (model prints are captured by pytest, so they do not reach here)."""
    seen = {m[1]: m[2] for m in PYTEST_LINE.finditer(out)}
    return {"passed": sum(v == "PASSED" for v in seen.values()),
            "failed": sum(v != "PASSED" for v in seen.values()),
            "collection_error": "ERROR collecting" in out or "errors during collection" in out or
                                bool(re.search(r"^ERROR .*test_task\.py", out, re.M)),
            "names": seen}


def classify(rc: int, elapsed: float, parsed: dict, out: str) -> str:
    """ok | wrong_answer | import_error | timeout | killed | sandbox_error"""
    if rc in (124, 137) and elapsed >= RUN_TIMEOUT_S - 0.5:
        return "timeout"
    if rc == 137:
        return "killed"            # out of memory or process limit: the container's cgroup killed it
    if rc in (125, 126, 127) or (rc not in (0, 1, 2, 5) and not out.strip()):
        return "sandbox_error"
    if parsed["collection_error"] and not parsed["names"]:
        return "import_error"
    return "ok" if rc == 0 and parsed["passed"] and not parsed["failed"] else "wrong_answer"


class Sandbox:
    def __init__(self, docker_host: str | None = None, image: str = IMAGE):
        self.host, self.image = docker_host, image
        self._tests: dict[str, str] = {}
        self._home: str | None = None

    # ---- talking to docker (local, or over ssh)
    def _cmd(self, args: list[str]) -> list[str]:
        if not self.host:
            return ["docker", *args]
        return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", self.host, REMOTE_PATH + shlex.join(["docker", *args])]

    def docker(self, args: list[str], stdin: bytes | None = None, timeout: float = 60.0) -> subprocess.CompletedProcess:
        return subprocess.run(self._cmd(args), input=stdin, capture_output=True, timeout=timeout)

    def shell(self, script: str, stdin: bytes | None = None, timeout: float = 30.0) -> subprocess.CompletedProcess:
        """A fixed script on the docker host (staging test files only; never built from model output)."""
        cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", self.host, script] if self.host else ["sh", "-c", script]
        return subprocess.run(cmd, input=stdin, capture_output=True, timeout=timeout)

    def check(self) -> None:
        """Raise SandboxUnavailable unless docker answers and the image exists."""
        try:
            r = self.docker(["image", "inspect", self.image, "--format", "{{.Id}}"], timeout=30)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise SandboxUnavailable(f"docker not reachable ({e.__class__.__name__})") from e
        if r.returncode != 0:
            raise SandboxUnavailable("docker answered but the image %s is missing or docker is down: %s"
                                     % (self.image, (r.stderr or r.stdout).decode(errors="replace").strip()[-200:]))

    # ---- staging the test files (read-only copies)
    def stage(self, tests: dict[str, str]) -> None:
        for k in tests:
            safe_id(k)
        if self.host:
            home = self.shell('printf %s "$HOME"').stdout.decode().strip()
            if not home.startswith("/"):
                raise SandboxUnavailable("could not find the docker host's home directory")
            self._home = home
            d = f"{home}/{REMOTE_TESTS_DIR}"
            self.shell(f"mkdir -p {shlex.quote(d)}")
            for k, src in tests.items():
                r = self.shell(f"cat > {shlex.quote(f'{d}/test_{k}.py')}", stdin=src.encode())
                if r.returncode != 0:
                    raise SandboxUnavailable(f"could not copy the test file for {k} to the docker host")
            self._dir = d
        else:
            self._dir = tempfile.mkdtemp(prefix="codebench-tests-")
            for k, src in tests.items():
                (Path(self._dir) / f"test_{k}.py").write_text(src)
        self._tests = dict(tests)

    # ---- one run
    def run(self, task_id: str, code: str) -> dict:
        safe_id(task_id)
        if task_id not in self._tests:
            raise KeyError(f"test file for {task_id} was not staged")
        name = "codebench-" + uuid.uuid4().hex[:12]
        t0 = time.time()
        try:
            r = self.docker(run_args(name, f"{self._dir}/test_{task_id}.py", self.image), stdin=code.encode("utf-8"),
                            timeout=WATCHDOG_S)
            rc, out = r.returncode, r.stdout.decode("utf-8", "replace")
            err = r.stderr.decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            self.docker(["rm", "-f", name], timeout=30)
            return {"kind": "timeout", "passed": 0, "failed": 0, "elapsed": round(time.time() - t0, 2), "note": "watchdog"}
        except OSError as e:
            raise SandboxUnavailable(f"docker could not be started: {e}") from e
        elapsed = time.time() - t0
        parsed = parse_pytest(out)
        kind = classify(rc, elapsed, parsed, out)
        return {"kind": kind, "passed": parsed["passed"], "failed": parsed["failed"], "rc": rc, "elapsed": round(elapsed, 2),
                "collection_error": parsed["collection_error"], "tail": (out if kind != "ok" else "")[-300:],
                **({"stderr": err[-300:]} if kind == "sandbox_error" else {})}


# ---------------------------------------------------------------- self-test
BAD_SNIPPET = r'''
import os, socket, subprocess, sys
R = {}
def probe(name, fn):
    try:
        fn()
        R[name] = "ALLOWED"
    except BaseException as e:
        R[name] = "blocked: " + type(e).__name__

def net_ip():
    socket.create_connection(("1.1.1.1", 53), timeout=3).close()
def net_dns():
    socket.gethostbyname("example.com")
def write(path, mode="w"):
    def f():
        open(path, mode).close()
    return f
def not_root():
    if os.getuid() != 0:
        raise PermissionError("not root")      # blocked: the process has no root rights to abuse
def no_host_paths():
    for p in ("/Users", "/host", "/var/run/docker.sock", "/run/docker.sock"):
        if os.path.exists(p):
            raise FileNotFoundError(p)
    raise FileNotFoundError("none present")
def pid_limit():
    kids = []
    try:
        for _ in range(300):
            kids.append(subprocess.Popen(["sleep", "5"]))
    finally:
        for k in kids:
            k.kill()
def disk_cap():
    with open("/work/big", "wb") as f:
        for _ in range(64):
            f.write(b"x" * 1024 * 1024)
            f.flush()
def clean_env():
    bad = [k for k in os.environ if any(w in k.upper() for w in ("KEY", "TOKEN", "SECRET", "PASSWORD"))]
    if bad:
        raise RuntimeError(",".join(bad))
    raise FileNotFoundError("no secrets in the environment")

probe("net_ip", net_ip)
probe("net_dns", net_dns)
probe("write_root", write("/pwned"))
probe("write_etc", write("/etc/pwned"))
probe("write_usr", write("/usr/pwned"))
probe("write_testfile", write("/tests/test_task.py", "a"))
probe("write_tests_dir", write("/tests/new.py"))
probe("not_root", not_root)
probe("no_host_paths", no_host_paths)
probe("pid_limit", pid_limit)
probe("disk_cap", disk_cap)
probe("clean_env", clean_env)
'''
PROBES = ["net_ip", "net_dns", "write_root", "write_etc", "write_usr", "write_testfile", "write_tests_dir", "not_root",
          "no_host_paths", "pid_limit", "disk_cap", "clean_env"]
BAD_TESTS = "import solution\n\n" + "\n\n".join(
    f"def test_{p}():\n    assert solution.R[{p!r}].startswith('blocked'), solution.R[{p!r}]" for p in PROBES) + "\n"
HANG_SNIPPET = "while True:\n    pass\n"
HANG_TESTS = "import solution\n\ndef test_never():\n    assert True\n"
MEM_SNIPPET = "blob = b'x' * (1024 ** 3)\nblob2 = bytearray(blob)\n"
GOOD_SNIPPET = "def add(a, b):\n    return a + b\n"
GOOD_TESTS = "from solution import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"


def selftest(sb: Sandbox) -> dict:
    """Run the known-bad snippets and a good one. ok only if everything bad was blocked and a good one passes."""
    sb.check()
    sb.stage({"selftest_bad": BAD_TESTS, "selftest_hang": HANG_TESTS, "selftest_good": GOOD_TESTS})
    bad = sb.run("selftest_bad", BAD_SNIPPET)
    hang = sb.run("selftest_hang", HANG_SNIPPET)
    mem = sb.run("selftest_hang", MEM_SNIPPET)
    good = sb.run("selftest_good", GOOD_SNIPPET)
    res = {
        "probes_blocked": bad["kind"] == "ok" and bad["passed"] == len(PROBES) and bad["failed"] == 0,
        "probes_passed": f"{bad['passed']}/{len(PROBES)}",
        "infinite_loop_killed": hang["kind"] == "timeout",
        "memory_hog_killed": mem["kind"] in ("killed", "timeout") or (mem["kind"] == "wrong_answer" and mem["passed"] == 0),
        "good_snippet_passes": good["kind"] == "ok",
    }
    res["ok"] = all(v for k, v in res.items() if k != "probes_passed")
    if not res["probes_blocked"]:
        res["bad_tail"] = bad.get("tail", "")
    res["mem_kind"], res["hang_kind"] = mem["kind"], hang["kind"]
    return res


def build_image(sb: Sandbox) -> None:
    dockerfile = f"FROM {BASE_IMAGE}\nRUN pip install --no-cache-dir pytest=={PYTEST_VERSION}\n"
    r = sb.docker(["build", "-t", sb.image, "-"], stdin=dockerfile.encode(), timeout=600)
    if r.returncode != 0:
        raise SandboxUnavailable("image build failed: " + (r.stderr or r.stdout).decode(errors="replace")[-300:])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["selftest", "build-image", "check"])
    ap.add_argument("--docker-host", help="ssh name of the machine that runs docker (default: docker on this machine)")
    a = ap.parse_args()
    sb = Sandbox(a.docker_host)
    try:
        if a.cmd == "build-image":
            build_image(sb)
            print("built", sb.image)
        elif a.cmd == "check":
            sb.check()
            print("docker reachable, image present")
        else:
            res = selftest(sb)
            print(res)
            sys.exit(0 if res["ok"] else 1)
    except SandboxUnavailable as e:
        print("SANDBOX UNAVAILABLE:", e, file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
