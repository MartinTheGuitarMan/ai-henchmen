"""commit_message_files: the diff of a checked commit range, read with one fixed git diff, then commit_message (small)
or commit_message_multi (large). Always local."""
import inspect
import json
import threading

import pytest

from minions import gitdiff, server, tools
from minions.config import Config, Roster
from minions.errors import BadInput, Invented, PrivacyRefused, SchemaError, TooLong

from test_commit_staged import git, write


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    write(r, {"app/pager.py": "def page(items, n):\n    return items[0:n + 1]\n", "README.md": "# Demo\n"})
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "Start")
    git(r, "tag", "v1")
    write(r, {"app/pager.py": "def page(items, n):\n    return items[0:n]\n"})
    git(r, "commit", "-qam", "Fix page")
    write(r, {"README.md": "# Demo\n\nPaging fixed.\n"})
    git(r, "commit", "-qam", "Docs")
    return r


def reply(fake, subject="Fix off-by-one in page", body="The slice end was one too far."):
    fake.replies.append(json.dumps({"subject": subject, "body": body}))


# ---------------------------------------------------------------- the read
def test_reads_the_range_diff_of_several_commits(repo):
    d = gitdiff.read_range_diff(str(repo), "v1..HEAD")
    assert sorted(d.files) == ["README.md", "app/pager.py"] and d.commits == 2 and "n + 1" in d.diff and d.skipped == []
    assert gitdiff.read_range_diff(str(repo), "HEAD~1").files == ["README.md"]   # a single ref means REF..HEAD
    assert gitdiff.read_range_diff(str(repo), "HEAD~2..HEAD~1").files == ["app/pager.py"]


def test_binary_is_skipped_and_reported(repo):
    write(repo, {"logo.png": b"\x89PNG\x00\xff", "app/new.py": "x = 1\n"})
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "More")
    d = gitdiff.read_range_diff(str(repo), "v1..HEAD")
    assert d.skipped == [{"path": "logo.png", "reason": "binary"}] and "logo.png" not in d.diff


@pytest.mark.parametrize("spec", ["--output=x", "-x..HEAD", "HEAD:README.md", "v1...HEAD", "v1 HEAD", "v1;touch x", "$(id)", "",
                                  "..HEAD", "nope..HEAD", "v1..nope", "main^{tree}", "v1..HEAD..main", None, 5, "a" * 300])
def test_bad_ranges_are_refused(repo, spec):
    with pytest.raises(BadInput):
        gitdiff.read_range_diff(str(repo), spec)
    assert not (repo / "x").exists()


def test_a_ref_naming_a_blob_is_refused(repo):
    blob = git(repo, "rev-parse", "HEAD:README.md").decode().strip()
    with pytest.raises(BadInput):
        gitdiff.read_range_diff(str(repo), f"{blob}..HEAD")


def test_empty_range_and_no_common_ancestor(repo):
    with pytest.raises(BadInput, match="empty diff"):
        gitdiff.read_range_diff(str(repo), "HEAD..HEAD")
    git(repo, "checkout", "-q", "--orphan", "other")
    write(repo, {"z.txt": "z\n"})
    git(repo, "add", "z.txt")
    git(repo, "commit", "-qm", "Orphan")
    with pytest.raises(BadInput, match="merge-base"):
        gitdiff.read_range_diff(str(repo), "main..other")


def test_not_a_repo_and_not_a_folder(tmp_path):
    (tmp_path / "plain").mkdir()
    for folder in (str(tmp_path / "plain"), str(tmp_path / "missing"), ""):
        with pytest.raises(BadInput):
            gitdiff.read_range_diff(folder, "HEAD~1..HEAD")


def test_over_size_is_refused_not_cut(repo, monkeypatch):
    write(repo, {"big.txt": "".join(f"line {i} of a long file\n" for i in range(300))})
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "Big")
    monkeypatch.setattr(gitdiff, "MAX_RANGE_CHARS", 3000)
    with pytest.raises(BadInput, match="limit is 3000"):
        gitdiff.read_range_diff(str(repo), "v1..HEAD")


def test_git_env_cannot_redirect_the_read(repo, tmp_path, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    git(other, "init", "-q", "-b", "main")
    write(other, {"secret.py": "x = 1\n"})
    git(other, "add", "-A")
    git(other, "commit", "-qm", "S")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    monkeypatch.setenv("GIT_INDEX_FILE", str(other / ".git" / "index"))
    assert "secret.py" not in gitdiff.read_range_diff(str(repo), "v1..HEAD").files


def test_hostile_repo_config_runs_nothing(repo, tmp_path):
    marker = tmp_path / "ran"
    script = tmp_path / "evil.sh"
    script.write_text(f"#!/bin/sh\ntouch '{marker}'\ncat \"$1\"\n")
    script.chmod(0o755)
    write(repo, {".gitattributes": "*.py diff=evil\n"})
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "Attrs")
    cfgs = [("diff.external", str(script)), ("diff.evil.textconv", str(script)), ("diff.evil.command", str(script)),
            ("core.fsmonitor", str(script)), ("core.pager", f"touch '{marker}'"), ("core.hooksPath", str(tmp_path / "hooks")),
            ("alias.diff", f"!touch '{marker}'"), ("core.editor", str(script)), ("diff.submodule", "log"),
            ("core.attributesFile", str(tmp_path / "attrs")), ("include.path", str(tmp_path / "inc"))]
    for k, v in cfgs:
        git(repo, "config", k, v)
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    for h in ("post-checkout", "reference-transaction", "fsmonitor-watchman"):
        for d in (hooks, repo / ".git" / "hooks"):
            (d / h).write_text(f"#!/bin/sh\ntouch '{marker}'\n")
            (d / h).chmod(0o755)
    (tmp_path / "attrs").write_text("*.py diff=evil\n")
    (tmp_path / "inc").write_text(f"[diff]\n\texternal = {script}\n")
    d = gitdiff.read_range_diff(str(repo), "v1..HEAD")
    assert "items[0:n]" in d.diff and not marker.exists()


def test_reading_does_not_change_the_repo(repo):
    snap = lambda: (git(repo, "status", "--porcelain=v2"), git(repo, "rev-parse", "HEAD"), (repo / ".git" / "index").read_bytes())
    before = snap()
    gitdiff.read_range_diff(str(repo), "v1..HEAD")
    assert before == snap()


# ---------------------------------------------------------------- the tool, small path
def test_small_path_matches_commit_message(fake, cfg, repo):
    reply(fake)
    out = tools.commit_message_files(cfg, str(repo), "v1..HEAD", "Mention paging.")
    d = gitdiff.read_range_diff(str(repo), "v1..HEAD").diff
    reply(fake)
    tools.commit_message(cfg, d, "Mention paging.")
    assert out["subject"] == "Fix off-by-one in page" and out["steps"] == 1 and out["commits"] == 2
    assert fake.requests[0][1]["messages"] == fake.requests[1][1]["messages"]


@pytest.mark.parametrize("subject,exc", [("Fix the pager so that it stops returning one item too many at the end of a page", TooLong),
                                         ("Fixed the pager", SchemaError), ("Fixes the pager", SchemaError),
                                         ("Fix the pager.", SchemaError), ("", Exception), ("Fix pager in app/other.py", Invented)])
def test_small_path_catches_planted_bad_subjects(fake, cfg, repo, subject, exc):
    reply(fake, subject=subject)
    with pytest.raises(exc):
        tools.commit_message_files(cfg, str(repo), "v1..HEAD")


def test_small_path_refuses_an_invented_file_in_the_body(fake, cfg, repo):
    reply(fake, body="Also touches settings.yaml.")
    with pytest.raises(Invented):
        tools.commit_message_files(cfg, str(repo), "v1..HEAD")


def test_a_skipped_binary_the_model_never_saw_is_refused(fake, cfg, repo):
    write(repo, {"logo.png": b"\x89PNG\x00\xff"})
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "Logo")
    reply(fake, subject="Add logo.png and fix pager")
    with pytest.raises(Invented):
        tools.commit_message_files(cfg, str(repo), "v1..HEAD")


# ---------------------------------------------------------------- the tool, large path
def big_repo(repo):
    write(repo, {"src/a.py": "".join(f"def f{i}(x):\n    return x + {i}\n\n" for i in range(400)),
                 "src/b.py": "".join(f"def g{i}(x):\n    return x * {i}\n\n" for i in range(400))})
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "Big")


def dyn_multi(fake, subject="Add helpers in src/a.py and src/b.py"):
    def dyn(req):
        text = req["messages"][-1]["content"]
        if "lists the files of a large git diff" in text:
            return json.dumps({"subject": subject, "body": "Two new modules."})
        return json.dumps({"summary": "Adds helper functions."})
    fake.dynamic = dyn


def test_large_path_uses_the_multi_tool(fake, cfg, repo):
    big_repo(repo)
    dyn_multi(fake)
    out = tools.commit_message_files(cfg, str(repo), "v1..HEAD")
    assert out["subject"].startswith("Add helpers") and out["steps"] > 1 and set(out["files"]) >= {"src/a.py", "src/b.py"}
    ref = tools.commit_message_multi(cfg, gitdiff.read_range_diff(str(repo), "v1..HEAD").diff)
    assert ref["subject"] == out["subject"] and ref["steps"] == out["steps"]


@pytest.mark.parametrize("subject,exc", [("Add helpers in src/other.py", Invented), ("Added helpers", SchemaError), ("Add helpers.", SchemaError)])
def test_large_path_catches_planted_bad_subjects(fake, cfg, repo, subject, exc):
    big_repo(repo)
    dyn_multi(fake, subject)
    with pytest.raises(exc):
        tools.commit_message_files(cfg, str(repo), "v1..HEAD")


# ---------------------------------------------------------------- privacy, input errors, route, concurrency
def test_input_errors_call_no_model(fake, cfg, repo, tmp_path):
    for folder, rng in ((str(tmp_path), "v1..HEAD"), (str(repo), "HEAD..HEAD"), (str(repo), "--output=x")):
        with pytest.raises(BadInput):
            tools.commit_message_files(cfg, folder, rng)
    with pytest.raises(BadInput):
        tools.commit_message_files(cfg, str(repo), "v1..HEAD", hint="x" * 301)
    assert fake.requests == []


def test_cloud_only_route_is_refused_before_git_runs(fake, repo, monkeypatch):
    cloud = Config(backend="lmstudio", base_url=fake.url, model="m", timeout=5, cloud=True, name="c")
    monkeypatch.setattr(gitdiff, "_git", lambda *a, **k: pytest.fail("git was called"))
    with pytest.raises(PrivacyRefused):
        tools.commit_message_files(Roster.single(cloud), str(repo), "v1..HEAD")
    assert fake.requests == []


def test_has_no_sensitive_parameter():
    assert "sensitive" not in inspect.signature(tools.commit_message_files).parameters
    assert "sensitive" not in inspect.signature(server.commit_message_files).parameters


def test_borrows_the_commit_message_route():
    cfg = lambda n: {"backend": "lmstudio", "base_url": "http://127.0.0.1:1/v1", "model": n}
    raw = {"models": {"a": cfg("a"), "b": cfg("b")},
           "routes": {"classify": {"fast": ["a"]}, "extract": {"fast": ["a"]}, "summarize": {"fast": ["a"]},
                      "commit_message": {"fast": ["b"]}}}
    assert Roster.from_dict(raw).route("commit_message_files").fast[0].name == "b"


def test_concurrent_calls_on_one_route(fake, cfg, repo):
    fake.dynamic = lambda body: json.dumps({"subject": "Fix off-by-one in page", "body": ""})
    fake.delay = 0.05
    res, errs = [], []

    def go():
        try:
            res.append(tools.commit_message_files(cfg, str(repo), "v1..HEAD")["subject"])
        except Exception as e:   # noqa: BLE001
            errs.append(e)

    ts = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs and res == ["Fix off-by-one in page"] * 6
