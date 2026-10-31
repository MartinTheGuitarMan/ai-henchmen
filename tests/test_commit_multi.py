"""commit_message_multi: a large diff is split in code, summarised piece by piece, and one message is written from the
summaries; commit_message's checks run on the final message against the whole diff."""
import json
import threading

import pytest

from minions import commit_multi as cm, server, tools
from minions.config import Config, Roster
from minions.errors import BadInput, EmptyValue, Invented, PrivacyRefused, SchemaError, TooLong


def body_text(n, tag):
    return "".join(f"+    value_{tag}_{i} = compute({i})\n" for i in range(n))


def file_diff(path, n=200, tag="a", new=False, old_text="-    old = 1\n"):
    head = f"diff --git a/{path} b/{path}\n" + ("new file mode 100644\n" if new else "") + "index 1111111..2222222 100644\n"
    return head + f"--- a/{path}\n+++ b/{path}\n@@ -1,1 +{1},{n} @@\n" + ("" if new else old_text) + body_text(n, tag)


LOCK = "diff --git a/uv.lock b/uv.lock\nindex 1..2 100644\n--- a/uv.lock\n+++ b/uv.lock\n@@ -1,3 +1,3 @@\n" + \
    "".join(f"-version = \"1.{i}\"\n+version = \"2.{i}\"\n" for i in range(3000))
BIG = file_diff("src/pager.py", 150, "p") + file_diff("src/cache.py", 150, "c") + file_diff("docs/guide.md", 40, "g")


def answer(fake, subject="Fix paging and add a cache", body="The pager slice and the cache are updated.", summary="Updates the module."):
    seen = {"final": 0, "steps": 0, "data": []}

    def dyn(req):
        text = req["messages"][-1]["content"]
        if "lists the files of a large git diff" in text:
            seen["final"] += 1
            seen["data"].append(text)
            return json.dumps({"subject": subject, "body": body})
        seen["steps"] += 1
        return json.dumps({"summary": summary})
    fake.dynamic = dyn
    return seen


# ---------------------------------------------------------------- planning in code
def test_split_files_statuses():
    d = (file_diff("a.py", 3) + "diff --git a/old.py b/new.py\nsimilarity index 100%\nrename from old.py\nrename to new.py\n"
         "diff --git a/logo.png b/logo.png\nnew file mode 100644\nindex 0..1\nBinary files /dev/null and b/logo.png differ\n"
         "diff --git a/gone.py b/gone.py\ndeleted file mode 100644\nindex 1..0\n--- a/gone.py\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-x\n-y\n"
         "diff --git a/run.sh b/run.sh\nold mode 100644\nnew mode 100755\n")
    fs = {f.path: f for f in cm.split_files(d)}
    assert [f.status for f in fs.values()] == ["modified", "renamed", "binary", "deleted", "mode"]
    assert fs["new.py"].old == "old.py" and fs["a.py"].added == 3 and fs["a.py"].removed == 1 and fs["gone.py"].removed == 2


def test_a_diff_header_inside_added_content_does_not_split():
    d = "diff --git a/t.py b/t.py\n--- a/t.py\n+++ b/t.py\n@@ -0,0 +1,2 @@\n+diff --git a/x.py b/x.py\n+print(1)\n"
    assert [f.path for f in cm.split_files(d)] == ["t.py"]


def test_big_files_are_split_without_losing_a_line():
    f = cm.split_files(file_diff("src/big.py", 700, "z"))[0]
    pieces = cm._split_big(f.text)
    assert len(pieces) > 1 and all(len(p) <= cm.PIECE_MAX for p in pieces)
    assert all(p.startswith("diff --git a/src/big.py") for p in pieces)
    assert all(f"value_z_{i} = compute({i})" in "".join(pieces) for i in range(700))


def test_plan_sends_mechanical_files_to_code():
    files = {f.path: f for f in cm.plan(BIG + LOCK)}
    assert files["uv.lock"].pieces == [] and "lock file" in files["uv.lock"].mechanical
    assert all(files[p].pieces for p in ("src/pager.py", "src/cache.py", "docs/guide.md"))


# ---------------------------------------------------------------- the tool
def test_large_diff_end_to_end(fake, cfg):
    assert len(BIG + LOCK) > 12000
    seen = answer(fake)
    out = tools.commit_message_multi(cfg, BIG + LOCK)
    assert out["subject"] == "Fix paging and add a cache" and out["files"] == ["src/pager.py", "src/cache.py", "docs/guide.md", "uv.lock"]
    assert seen["final"] == 1 and seen["steps"] == out["steps"] and out["steps"] >= 3
    data = seen["data"][0]
    assert "uv.lock" in data and "lock file regenerated" in data and "Updates the module." in data
    assert "version = " not in data   # the lock file's content never reaches a model
    assert data.index("src/pager.py") < data.index("uv.lock")   # generated files are listed last


def test_the_final_step_sees_only_summaries(fake, cfg):
    seen = answer(fake, summary="Adds value computations.")
    tools.commit_message_multi(cfg, BIG)
    assert "compute(" not in seen["data"][0]


def test_hint_reaches_the_final_step_only(fake, cfg):
    answer(fake)
    tools.commit_message_multi(cfg, BIG, hint="Mention the pager.")
    finals = [r for _, r in fake.requests if "lists the files of a large" in r["messages"][-1]["content"]]
    assert len(finals) == 1 and "Mention the pager." in finals[0]["messages"][-1]["content"]
    assert not any("Mention the pager." in r["messages"][-1]["content"] for _, r in fake.requests if r not in finals)


def test_message_may_name_a_file_of_the_whole_diff(fake, cfg):
    answer(fake, body="Touches src/cache.py and docs/guide.md.")
    assert tools.commit_message_multi(cfg, BIG)["body"].startswith("Touches")


@pytest.mark.parametrize("subject,exc", [
    ("", EmptyValue), ("Fix " + "x" * 80, TooLong), ("Fixed the paging", SchemaError), ("Fixes the paging", SchemaError),
    ("Fixing the paging", SchemaError), ("Fix the paging.", SchemaError), ("Fix paging\nand more", SchemaError),
    ("Fix paging in src/other.py", Invented)])
def test_final_check_catches_planted_bad_subjects(fake, cfg, subject, exc):
    answer(fake, subject=subject, body="")
    with pytest.raises(exc):
        tools.commit_message_multi(cfg, BIG)


def test_final_check_catches_an_invented_file_in_the_body(fake, cfg):
    answer(fake, body="Also updates utils/dates.py.")
    with pytest.raises(Invented):
        tools.commit_message_multi(cfg, BIG)


def test_a_step_summary_that_invents_never_reaches_the_final_step(fake, cfg):
    for bad in ("Rewrites src/engine.py.", "Raises the limit to 9999.", "  ", "word " * 70):
        seen = answer(fake, summary=bad)
        out = tools.commit_message_multi(cfg, BIG)
        assert out["code_summaries"] == out["steps"] >= 3 and seen["final"] == 1
        data = seen["data"][0]
        assert "no model summary" in data and "src/engine.py" not in data and "9999" not in data and "word word" not in data
        assert "functions or classes added" not in data   # BIG has no def lines; names only come from the diff itself


def test_a_rejected_summary_gets_one_repair_try(fake, cfg):
    state = {"n": 0}
    seen = answer(fake)
    inner = fake.dynamic

    def dyn(req):
        text = req["messages"][-1]["content"]
        if "previous summary used terms" in text:
            state["n"] += 1
            return json.dumps({"summary": "Adds value computations."})
        if "lists the files of a large git diff" not in text and state["n"] == 0 and "src/pager.py" in text:
            return json.dumps({"summary": "Raises the limit to 9999."})
        return inner(req)
    fake.dynamic = dyn
    out = tools.commit_message_multi(cfg, BIG)
    assert state["n"] == 1 and out["code_summaries"] == 0


def test_code_summary_uses_only_the_pieces_own_names_and_counts():
    piece = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1,3 @@\n-x = 1\n+def parse(a):\n+    return a\n+class Box:\n"
    s = cm.code_summary(piece)
    assert "+3 -1" in s and "parse, Box" in s


def test_input_checks_refuse_and_never_cut(fake, cfg):
    with pytest.raises(BadInput):
        tools.commit_message_multi(cfg, "just some text")
    with pytest.raises(BadInput):   # over the total cap
        tools.commit_message_multi(cfg, BIG + "+" + "x" * cm.MAX_TOTAL)
    with pytest.raises(BadInput):   # too many files
        tools.commit_message_multi(cfg, "".join(file_diff(f"f{i}.py", 3) for i in range(cm.MAX_FILES + 1)))
    with pytest.raises(BadInput):   # one file that needs more than the pieces allowed
        tools.commit_message_multi(cfg, file_diff("src/huge.py", 2500))
    with pytest.raises(BadInput):
        tools.commit_message_multi(cfg, BIG, hint="x" * 301)
    assert fake.requests == []


def test_a_cap_sized_lock_file_alone_needs_no_model_step(fake, cfg):
    seen = answer(fake, subject="Bump locked dependencies", body="")
    out = tools.commit_message_multi(cfg, LOCK)
    assert out["steps"] == 0 and seen["final"] == 1 and seen["steps"] == 0


def test_cloud_only_route_is_refused_unless_not_sensitive(fake):
    cloud = Config(backend="lmstudio", base_url=fake.url, model="m", timeout=5, cloud=True, name="c")
    with pytest.raises(PrivacyRefused):
        tools.commit_message_multi(Roster.single(cloud), BIG)
    assert fake.requests == []
    answer(fake)
    assert tools.commit_message_multi(Roster.single(cloud), BIG, sensitive=False)["subject"]


def test_sensitive_is_the_default_in_both_layers():
    import inspect
    for fn in (tools.commit_message_multi, server.commit_message_multi):
        assert inspect.signature(fn).parameters["sensitive"].default is True


def test_borrows_the_commit_message_route():
    cfg = lambda n: {"backend": "lmstudio", "base_url": "http://127.0.0.1:1/v1", "model": n}
    raw = {"models": {"a": cfg("a"), "b": cfg("b"), "c": cfg("c")},
           "routes": {"classify": {"fast": ["a"]}, "extract": {"fast": ["a"]}, "summarize": {"fast": ["a"]},
                      "commit_message": {"fast": ["b"], "fallback": ["c"]}}}
    r = Roster.from_dict(raw)
    assert r.route("commit_message_multi").fast[0].name == "b" and r.route("commit_message_multi").fallback[0].name == "c"


def test_concurrent_calls_on_one_route(fake, cfg):
    answer(fake)
    fake.delay = 0.02
    res, errs = [], []

    def go():
        try:
            res.append(tools.commit_message_multi(cfg, BIG)["subject"])
        except Exception as e:   # noqa: BLE001
            errs.append(e)

    ts = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs and res == ["Fix paging and add a cache"] * 4


def test_reads_nothing_but_its_argument():
    import inspect
    src = inspect.getsource(cm) + inspect.getsource(tools.commit_message_multi)
    for word in ("subprocess", "open(", "read_text", "gitdiff", "Path("):
        assert word not in src
