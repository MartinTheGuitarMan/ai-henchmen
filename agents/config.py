"""Agent settings, from an optional JSON file (MINION_AGENTS_CONFIG, default ~/.config/minions/agents.json).

Which repos an agent may work on is not set here: that is the privacy map's job (`minions/privacy.py`). Only a
repo whose class is `low` is allowed, so with no map file no repo is.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG = "~/.config/minions/agents.json"
DEFAULT_RUNS = "~/.cache/minions/agent-runs"

# Approval mode per role. auto_edit approves file edits (in the clone only); shell commands are governed by the
# policy file. default approves nothing beyond the policy, so the reviewer can read and run tests but not edit.
ROLE_APPROVAL = {"default": "auto_edit", "codereviewer": "default"}


@dataclass
class GeminiSettings:
    command: str = "gemini"
    model: str | None = None  # None: the CLI's own default
    timeout_s: int = 900
    sandbox: bool = True
    max_response_chars: int = 20_000


@dataclass
class AgentConfig:
    gemini: GeminiSettings = field(default_factory=GeminiSettings)
    runs_dir: Path = field(default_factory=lambda: Path(DEFAULT_RUNS).expanduser())
    # Repos whose unpushed commits count as public (for example ones holding only invented data). Every other
    # repo must have its base commit on a remote-tracking branch, because unpushed work is not yet public.
    unpushed_ok_repos: list[Path] = field(default_factory=list)

    def unpushed_ok(self, repo: Path) -> bool:
        repo = repo.resolve()
        return any(repo == p for p in self.unpushed_ok_repos)


def config_path() -> Path:
    return Path(os.environ.get("MINION_AGENTS_CONFIG") or DEFAULT_CONFIG).expanduser()


def load(path: Path | None = None) -> AgentConfig:
    path = path or config_path()
    if not path.exists():
        return AgentConfig()
    raw = json.loads(path.read_text(encoding="utf-8"))
    conf = AgentConfig(gemini=GeminiSettings(**raw.get("gemini", {})))
    if "runs_dir" in raw:
        conf.runs_dir = Path(raw["runs_dir"]).expanduser()
    conf.unpushed_ok_repos = [Path(p).expanduser().resolve() for p in raw.get("unpushed_ok_repos", [])]
    return conf
