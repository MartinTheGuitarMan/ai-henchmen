"""Privacy class of a source path, from an optional map file. No model: a script reads the map and matches paths.

The map can only tighten: `tighten` never turns a sensitive call into a non-sensitive one. No map file keeps the
old behaviour exactly. A map that exists but cannot be read, parsed or validated fails closed: every source counts
as "personal". The real map is written elsewhere; this module only reads it.

Format: {"version": 1, "default": "personal", "paths": [{"path": "/absolute/path", "class": "low"}]}
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

CLASSES = ("low", "personal", "restricted")
VERSION = 1
DEFAULT_MAP = "~/.config/minions/privacy-map.json"
_FOLD = sys.platform in ("darwin", "win32")   # default filesystems there ignore case


@dataclass(frozen=True)
class PrivacyMap:
    state: str                                  # "absent", "ok" or "invalid"
    default: str = "personal"
    entries: tuple[tuple[str, str], ...] = ()   # (resolved absolute path, class)
    problem: str = ""


def _key(p: str) -> str:
    return p.casefold() if _FOLD else p


def _resolve(p: str) -> str:
    return os.path.realpath(os.path.expanduser(p))


def map_path() -> Path:
    return Path(os.environ.get("MINION_PRIVACY_MAP") or DEFAULT_MAP).expanduser()


def _parse(raw: object) -> PrivacyMap:
    if not isinstance(raw, dict) or raw.get("version") != VERSION or isinstance(raw.get("version"), bool):
        return PrivacyMap("invalid", problem="unknown or missing version")
    default = raw.get("default", "personal")
    if default not in CLASSES:
        return PrivacyMap("invalid", problem="bad default class")
    paths = raw.get("paths", [])
    if not isinstance(paths, list):
        return PrivacyMap("invalid", problem="paths must be a list")
    entries = []
    for e in paths:
        if not isinstance(e, dict) or not isinstance(e.get("path"), str) or e.get("class") not in CLASSES:
            return PrivacyMap("invalid", problem="bad path entry")
        if not os.path.isabs(os.path.expanduser(e["path"])):
            return PrivacyMap("invalid", problem="path entries must be absolute")
        entries.append((_resolve(e["path"]), e["class"]))
    return PrivacyMap("ok", default, tuple(entries))


def load_map() -> PrivacyMap:
    p = map_path()
    if not p.exists() and not p.is_symlink():
        return PrivacyMap("absent")
    try:
        return _parse(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return PrivacyMap("invalid", problem="unreadable or not JSON")


def _under(target: str, prefix: str) -> bool:
    t, q = _key(target), _key(prefix).rstrip(os.sep)
    return t == q or t.startswith(q + os.sep)


def class_of(path: str, pmap: PrivacyMap | None = None) -> dict:
    pmap = pmap or load_map()
    if not isinstance(path, str) or not path.strip():
        from .errors import BadInput
        raise BadInput("path must be a non-empty string")
    real = _resolve(path)
    if pmap.state == "invalid":
        return {"path": real, "class": "personal", "matched": None, "map": "invalid"}
    if pmap.state == "absent":
        return {"path": real, "class": "personal", "matched": None, "map": "absent"}
    best = None
    for prefix, cls in pmap.entries:
        if _under(real, prefix):
            rank = (len(_key(prefix).rstrip(os.sep)), CLASSES.index(cls))   # longest prefix; on a tie the stricter class
            if best is None or rank > best[0]:
                best = (rank, prefix, cls)
    if best:
        return {"path": real, "class": best[2], "matched": best[1], "map": "ok"}
    return {"path": real, "class": pmap.default, "matched": None, "map": "ok"}


def tighten(sensitive: bool, *sources: str | None) -> bool:
    """True if the call was already sensitive or any source path is labelled above "low". With no map file, or no
    source, the caller's flag is returned unchanged. It never returns False for True."""
    if sensitive:
        return True
    pmap = load_map()
    if pmap.state == "absent":
        return sensitive
    return any(class_of(s, pmap)["class"] != "low" for s in sources if isinstance(s, str) and s.strip())
