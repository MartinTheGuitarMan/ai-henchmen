"""Privacy map: a script lookup of a path's class, and a gate that can only tighten. Invented paths and data."""
import json
import os
import subprocess

import pytest

from minions import backends, privacy, ratelimit, server
from minions.config import Roster
from minions.errors import PrivacyRefused

KEY = "MINION_TEST_KEY"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    ratelimit.reset()
    monkeypatch.setenv(KEY, "secret-test-key")
    monkeypatch.setattr(backends.time, "sleep", lambda s: None)


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Invented tree: repo-a (personal), repo-a/pub (low), repo-b (restricted), repo-a-other (unlabelled)."""
    for d in ("repo-a/pub", "repo-b", "repo-a-other", "elsewhere"):
        (tmp_path / d).mkdir(parents=True)
        (tmp_path / d / "note.md").write_text("Invented note about the Orchid project.\n")
    mp = tmp_path / "map.json"
    mp.write_text(json.dumps({"version": 1, "default": "personal", "paths": [
        {"path": str(tmp_path / "repo-a"), "class": "personal"},
        {"path": str(tmp_path / "repo-a" / "pub"), "class": "low"},
        {"path": str(tmp_path / "repo-b"), "class": "restricted"},
        {"path": str(tmp_path / "elsewhere"), "class": "low"}]}))
    monkeypatch.setenv("MINION_PRIVACY_MAP", str(mp))
    return tmp_path, mp


def cls(p):
    return privacy.class_of(str(p))["class"]


# ---------- lookup ----------
def test_longest_prefix_and_default(world):
    t, _ = world
    assert cls(t / "repo-a/note.md") == "personal"
    assert cls(t / "repo-a/pub/note.md") == "low"        # the longer label wins over its parent
    assert cls(t / "repo-b/note.md") == "restricted"
    assert cls(t / "repo-a-other/note.md") == "personal"  # unlabelled -> default
    assert cls(t / "not/there.md") == "personal"


def test_default_can_be_low(world):
    t, mp = world
    mp.write_text(json.dumps({"version": 1, "default": "low", "paths": [{"path": str(t / "repo-b"), "class": "restricted"}]}))
    assert cls(t / "repo-a/note.md") == "low" and cls(t / "repo-b/x") == "restricted"


def test_boundary_dodges(world):
    t, _ = world
    assert cls(t / "repo-b") == "restricted"                  # the root itself
    assert cls(str(t / "repo-b") + "/") == "restricted"       # trailing slash
    assert cls(t / "repo-b/sub/../note.md") == "restricted"   # ..
    assert cls(t / "elsewhere/../repo-b/note.md") == "restricted"   # .. out of a low folder into a restricted one
    assert cls(t / "repo-b-lookalike/note.md") == "personal"  # prefix look-alike is not under repo-b
    assert cls(t / "repo-a-other") == "personal"


def test_symlinks_cannot_dodge(world):
    t, _ = world
    os.symlink(t / "repo-b", t / "elsewhere" / "link")        # a link sitting in a low folder, pointing into a restricted one
    assert cls(t / "elsewhere/link/note.md") == "restricted"
    os.symlink(t / "elsewhere", t / "repo-b" / "outlink")     # a link in a restricted folder pointing to a low one
    assert cls(t / "repo-b/outlink/note.md") == "low"         # the real path decides, not where the link sits


def test_entry_symlink_is_resolved(world):
    t, mp = world
    os.symlink(t / "repo-b", t / "alias")
    mp.write_text(json.dumps({"version": 1, "default": "low", "paths": [{"path": str(t / "alias"), "class": "restricted"}]}))
    assert cls(t / "repo-b/note.md") == "restricted"


def test_tilde_and_relative_input(world, monkeypatch):
    t, _ = world
    monkeypatch.chdir(t / "repo-b")
    assert cls("note.md") == "restricted"


# ---------- corrupt / absent ----------
@pytest.mark.parametrize("content", [
    "not json", "[]", "{}", json.dumps({"version": 2, "paths": []}), json.dumps({"version": True, "paths": []}),
    json.dumps({"version": 1, "default": "public", "paths": []}),
    json.dumps({"version": 1, "paths": [{"path": "relative/dir", "class": "low"}]}),
    json.dumps({"version": 1, "paths": [{"path": "/abs", "class": "secret"}]}),
    json.dumps({"version": 1, "paths": "oops"}), json.dumps({"version": 1, "paths": [3]}),
])
def test_corrupt_map_fails_closed(world, content):
    t, mp = world
    mp.write_text(content)
    for p in (t / "elsewhere/note.md", t / "repo-a/pub/note.md"):
        assert privacy.class_of(str(p)) ["class"] == "personal" and privacy.class_of(str(p))["map"] == "invalid"
        assert privacy.tighten(False, str(p)) is True


def test_unreadable_map_fails_closed(world):
    t, mp = world
    mp.chmod(0)
    try:
        if os.access(mp, os.R_OK):
            pytest.skip("running as a user who can read anything")
        assert privacy.tighten(False, str(t / "elsewhere/note.md")) is True
    finally:
        mp.chmod(0o600)


def test_no_map_keeps_todays_behaviour(tmp_path, monkeypatch):
    monkeypatch.setenv("MINION_PRIVACY_MAP", str(tmp_path / "missing.json"))
    assert privacy.load_map().state == "absent"
    assert privacy.tighten(False, str(tmp_path / "x")) is False
    assert privacy.tighten(True, str(tmp_path / "x")) is True
    assert privacy.tighten(False) is False


def test_default_map_location(monkeypatch):
    monkeypatch.delenv("MINION_PRIVACY_MAP", raising=False)
    assert str(privacy.map_path()).endswith(".config/minions/privacy-map.json")


# ---------- tighten only ----------
def test_never_loosens(world):
    t, _ = world
    for p in (t / "elsewhere/note.md", t / "repo-b/note.md", t / "nowhere", ""):
        assert privacy.tighten(True, str(p)) is True        # sensitive in, sensitive out, even for a low source
    assert privacy.tighten(False, str(t / "elsewhere/note.md")) is False   # low source, caller said public: unchanged
    assert privacy.tighten(False, str(t / "repo-a/note.md")) is True
    assert privacy.tighten(False, str(t / "elsewhere/note.md"), str(t / "repo-b/note.md")) is True   # any non-low source
    assert privacy.tighten(False, "") is False and privacy.tighten(False, None) is False   # no source: the caller decides


def test_privacy_class_of_tool(world):
    t, _ = world
    out = server.privacy_class_of(str(t / "repo-b/sub/../note.md"))
    assert out["class"] == "restricted" and out["map"] == "ok" and out["matched"] == str(t.resolve() / "repo-b")
    with pytest.raises(Exception):
        server.privacy_class_of("  ")


# ---------- the gate, tool by tool: a cloud-only roster, so reaching a model means reaching the cloud ----------
def outcome(call) -> str:
    """What a call did: the error text if it raised, else its JSON result (batch tools report errors per item)."""
    try:
        return json.dumps(call())
    except Exception as e:
        return str(e)


def local_roster(fake):
    return Roster.from_dict({"models": {"l": {"backend": "lmstudio", "base_url": fake.url, "model": "l", "timeout": 5}}})


def cloud_roster(fake):
    return Roster.from_dict({"models": {"c": {"backend": "openai-compat", "base_url": fake.url, "model": "c",
                                              "timeout": 5, "cloud": True, "key_env": KEY,
                                              "knowledge": True}}})


SCHEMA = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
ITEMS = [{"id": "1", "text": "hello"}]
PLAIN = {   # every plain-text tool that takes `sensitive`, with minimal valid arguments
    "classify": lambda **kw: server.classify("hello", ["a", "b"], **kw),
    "extract": lambda **kw: server.extract("name is Orchid", SCHEMA, **kw),
    "summarize": lambda **kw: server.summarize("A short invented text.", **kw),
    "tag": lambda **kw: server.tag("hello", ["a", "b"], max_labels=2, **kw),
    "find_sensitive": lambda **kw: server.find_sensitive("hello", **kw),
    "same": lambda **kw: server.same("one", "two", **kw),
    "grounded": lambda **kw: server.grounded("claim", "source", **kw),
    "check_claims": lambda **kw: server.check_claims("claim", "source", **kw),
    "commit_message": lambda **kw: server.commit_message("diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n", **kw),
    "commit_message_multi": lambda **kw: server.commit_message_multi("diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n", **kw),
    "score": lambda **kw: server.score("hello", "polite", **kw),
    "translate": lambda **kw: server.translate("hello", "sv", **kw),
    "classify_batch": lambda **kw: server.classify_batch(ITEMS, ["a", "b"], **kw),
    "tag_batch": lambda **kw: server.tag_batch(ITEMS, ["a", "b"], max_labels=2, **kw),
    "ask": lambda **kw: server.ask("What is two plus two?", **kw),
}


@pytest.mark.parametrize("name", PLAIN)
@pytest.mark.parametrize("which", ["repo-a/note.md", "repo-b/note.md", "repo-a-other/note.md", "nowhere/at/all.md",
                                   "repo-b/sub/../note.md", "elsewhere/../repo-b/note.md"])
def test_non_low_source_never_reaches_cloud(world, fake, monkeypatch, name, which):
    t, _ = world
    monkeypatch.setattr(server.Roster, "from_env", classmethod(lambda cls, env=None: cloud_roster(fake)))
    assert "MINION_PRIVACY" in outcome(lambda: PLAIN[name](sensitive=False, source_path=str(t / which)))
    assert fake.requests == []


@pytest.mark.parametrize("name", PLAIN)
def test_low_source_with_sensitive_stays_local(world, fake, monkeypatch, name):
    t, _ = world
    monkeypatch.setattr(server.Roster, "from_env", classmethod(lambda cls, env=None: cloud_roster(fake)))
    for kw in ({"sensitive": True, "source_path": str(t / "elsewhere/note.md")}, {"source_path": str(t / "elsewhere/note.md")}, {}):
        assert "MINION_PRIVACY" in outcome(lambda: PLAIN[name](**kw)), kw
    assert fake.requests == []


@pytest.mark.parametrize("name", PLAIN)
def test_low_or_no_source_unchanged_when_public(world, fake, monkeypatch, name):
    """The map does not block what it should not: a low source (or none) with sensitive=false still reaches the cloud model."""
    t, _ = world
    monkeypatch.setattr(server.Roster, "from_env", classmethod(lambda cls, env=None: cloud_roster(fake)))
    for kw in ({"sensitive": False, "source_path": str(t / "elsewhere/note.md")}, {"sensitive": False}):
        fake.requests.clear()
        assert "MINION_PRIVACY" not in outcome(lambda: PLAIN[name](**kw))
        assert fake.requests, name


def test_no_map_means_public_call_reaches_cloud(tmp_path, fake, monkeypatch):
    monkeypatch.setenv("MINION_PRIVACY_MAP", str(tmp_path / "missing.json"))
    monkeypatch.setattr(server.Roster, "from_env", classmethod(lambda cls, env=None: cloud_roster(fake)))
    try:
        server.classify("hello", ["a", "b"], sensitive=False, source_path=str(tmp_path / "x"))
    except Exception as e:
        assert "MINION_PRIVACY" not in str(e)
    assert fake.requests


def test_corrupt_map_blocks_a_public_call_with_source(world, fake, monkeypatch):
    t, mp = world
    mp.write_text("{broken")
    monkeypatch.setattr(server.Roster, "from_env", classmethod(lambda cls, env=None: cloud_roster(fake)))
    with pytest.raises(Exception):
        server.classify("hello", ["a", "b"], sensitive=False, source_path=str(t / "elsewhere/note.md"))
    assert fake.requests == []


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test Author", "-c", "user.email=author@example.invalid",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)


@pytest.mark.parametrize("where", ["repo-b", "elsewhere"])   # restricted and low alike: path-aware tools are always local
def test_path_aware_tools_never_reach_cloud(world, fake, monkeypatch, where):
    t, _ = world
    monkeypatch.setattr(server.Roster, "from_env", classmethod(lambda cls, env=None: cloud_roster(fake)))
    d = t / where
    git(d, "init", "-q", "-b", "main")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "Start")
    (d / "note.md").write_text("Invented note, changed.\n")
    git(d, "add", "-A")
    calls = [
        lambda: server.classify_file(str(d / "note.md"), ["a", "b"]),
        lambda: server.extract_file(str(d / "note.md"), SCHEMA),
        lambda: server.summarize_file(str(d / "note.md")),
        lambda: server.classify_files(str(d), "*.md", ["a", "b"]),
        lambda: server.tag_files(str(d), "*.md", ["a", "b"], 2),
        lambda: server.scan_diff(str(d), "HEAD~0"),
        lambda: server.commit_message_staged(str(d)),
    ]
    for call in calls:
        assert "MINION_PRIVACY" in outcome(call)
    assert fake.requests == []


def test_path_aware_tools_use_the_map(world, fake, monkeypatch):
    """Each path-aware tool asks the map about its source: the check is wired in, not only implied by always-local."""
    t, _ = world
    monkeypatch.setattr(server.Roster, "from_env", classmethod(lambda cls, env=None: local_roster(fake)))
    seen = []
    real = privacy.tighten
    monkeypatch.setattr(privacy, "tighten", lambda s, *src: (seen.append(src), real(s, *src))[1])
    d = t / "repo-b"
    for call in (lambda: server.classify_file(str(d / "note.md"), ["a"]), lambda: server.extract_file(str(d / "note.md"), SCHEMA),
                 lambda: server.summarize_file(str(d / "note.md")), lambda: server.classify_files(str(d), "*.md", ["a"]),
                 lambda: server.tag_files(str(d), "*.md", ["a"], 1), lambda: server.scan_diff(str(d), "HEAD"),
                 lambda: server.commit_message_staged(str(d))):
        before = len(seen)
        outcome(call)
        assert len(seen) > before and any(str(d) in s[0] for s in seen[before:] if s)


# ---------- the planted bad case: a gate that loosens, or ignores the map, must fail these tests ----------
def test_planted_loosening_gate_is_caught(world, fake, monkeypatch):
    t, _ = world
    monkeypatch.setattr(server.Roster, "from_env", classmethod(lambda cls, env=None: cloud_roster(fake)))
    monkeypatch.setattr(privacy, "tighten", lambda sensitive, *sources: sensitive)   # ignores the map
    try:
        server.classify("hello", ["a", "b"], sensitive=False, source_path=str(t / "repo-b/note.md"))
    except Exception:
        pass
    assert fake.requests, "a gate that ignores the map lets a restricted source reach the cloud: the tests above would catch it"
    monkeypatch.setattr(privacy, "tighten", lambda sensitive, *sources: False)       # turns sensitive into public
    assert privacy.tighten(True, str(t / "repo-b")) is False   # what test_never_loosens asserts against
