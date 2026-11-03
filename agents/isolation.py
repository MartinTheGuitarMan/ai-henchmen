"""Throwaway clones: the agent works on a copy with no remote, never on the repo itself."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


class IsolationError(RuntimeError):
    pass


def _git(args: list[str], cwd: Path, check: bool = True) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env)
    if check and proc.returncode != 0:
        raise IsolationError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def repo_root(path: Path) -> Path:
    try:
        return Path(_git(["rev-parse", "--show-toplevel"], cwd=path).strip()).resolve()
    except (IsolationError, FileNotFoundError, NotADirectoryError) as exc:
        raise IsolationError(f"{path} is not a git repository") from exc


def make_clone(repo: Path, dest: Path, base: str, branch: str) -> None:
    """Clone repo into dest, drop the remote, start branch at commit base (already resolved)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    _git(["clone", "--quiet", "--no-hardlinks", "--no-checkout", str(repo), str(dest)], cwd=dest.parent)
    _git(["remote", "remove", "origin"], cwd=dest)
    _git(["checkout", "--quiet", "-b", branch, base], cwd=dest)
    _git(["config", "user.name", "agent"], cwd=dest)
    _git(["config", "user.email", "agent@localhost"], cwd=dest)


def is_pushed(repo: Path, commit: str) -> bool:
    """True if commit is on at least one remote-tracking branch (as last fetched), i.e. already public."""
    return bool(_git(["branch", "-r", "--contains", commit], cwd=repo).strip())


def resolve_commit(repo: Path, ref: str) -> str:
    if ref.startswith("-"):
        raise IsolationError(f"bad ref {ref!r}")
    return _git(["rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"], cwd=repo).strip()


def collect_diff(clone: Path, base: str) -> tuple[str, str, list[str]]:
    """Everything the agent changed relative to base, committed or not.

    Returns (binary patch, --stat text, commits the agent made).
    """
    _git(["add", "-A"], cwd=clone)
    patch = _git(["diff", "--cached", "--binary", base], cwd=clone)
    stat = _git(["diff", "--cached", "--stat", base], cwd=clone)
    commits = _git(["log", "--format=%h %s", f"{base}..HEAD"], cwd=clone).splitlines()
    return patch, stat, commits
