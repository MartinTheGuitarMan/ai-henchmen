"""failure_histogram: ranks check_failed codes from JSONL logs. Plain code; checked against an independent Counter."""
import json
import random
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import failure_histogram as fh  # noqa: E402


def rec(status="ok", code=None, model="m1", tool="t"):
    return {"status": status, "code": code, "model": model, "tool": tool, "case": "c", "rep": 0}


def put(tmp_path, name, recs):
    p = tmp_path / name
    p.write_text("".join(json.dumps(r) + "\n" for r in recs))
    return str(p)


FAIL = lambda code, **kw: rec("check_failed", code, **kw)
SETS = [
    [FAIL("MINION_INVENTED")],
    [FAIL("MINION_INVENTED"), FAIL("MINION_SCHEMA"), FAIL("MINION_INVENTED")],
    [FAIL("MINION_SCHEMA"), FAIL("MINION_INVENTED")],                       # tie: ordered by code
    [rec("ok"), rec("wrong"), FAIL("MINION_TOO_LONG")],
    [rec("not_run"), rec("not_run"), FAIL("MINION_EMPTY")],
    [rec("ok")] * 5,
    [FAIL(None)],
    [FAIL("MINION_SCHEMA", model="a"), FAIL("MINION_SCHEMA", model="b"), FAIL("MINION_SCHEMA", model="a")],
    [FAIL("X", tool="score"), FAIL("Y", tool="check_claims"), FAIL("Y", tool="check_claims")],
    [rec("wrong")] * 3 + [FAIL("MINION_NOT_IN_SOURCE")] * 2,
    [FAIL("B"), FAIL("A"), FAIL("C"), FAIL("A"), FAIL("C")],
    [FAIL("MINION_INVENTED", model="z")] * 4 + [FAIL("MINION_TOO_LONG")] * 4,
]


@pytest.mark.parametrize("recs", SETS)
def test_equals_an_independent_count(tmp_path, recs):
    h = fh.histogram(fh.load([put(tmp_path, "r.jsonl", recs)]))
    indep = Counter((r["code"] or "-") for r in recs if r["status"] == "check_failed")
    assert [(c, n) for c, n, _ in h["rows"]] == sorted(indep.items(), key=lambda t: (-t[1], t[0]))
    assert h["failures"] == sum(indep.values()) and h["records"] == len(recs)
    assert h["other"] == dict(Counter(r["status"] for r in recs if r["status"] != "check_failed"))


def test_random_logs_across_files_and_a_folder(tmp_path):
    rnd = random.Random(7)
    allrecs = []
    for i in range(4):
        part = [rec(rnd.choice(["ok", "wrong", "not_run", "check_failed"]), rnd.choice(["A", "B", "C", None]),
                    model=rnd.choice(["m1", "m2"])) for _ in range(60)]
        put(tmp_path, f"f{i}.jsonl", part)
        allrecs += part
    h = fh.histogram(fh.load([str(tmp_path)]))
    indep = Counter((r["code"] or "-") for r in allrecs if r["status"] == "check_failed")
    assert {c: n for c, n, _ in h["rows"]} == dict(indep) and h["records"] == 240


def test_filters_by_tool_and_model(tmp_path):
    p = put(tmp_path, "r.jsonl", SETS[8] + [FAIL("Y", tool="score", model="b")])
    assert fh.histogram(fh.load([p]), tool="check_claims")["rows"][0][:2] == ("Y", 2)
    assert fh.histogram(fh.load([p]), model="b")["failures"] == 1


def test_render_table(tmp_path):
    text = fh.render(fh.histogram(fh.load([put(tmp_path, "r.jsonl", SETS[7] + [rec("not_run")])])))
    assert "| 1 | MINION_SCHEMA | 3 | 100% | a 2, b 1 |" in text and "3 failures in 4 records; other statuses: not_run 1" in text


def test_no_failures_is_said(tmp_path):
    assert "no failures" in fh.render(fh.histogram(fh.load([put(tmp_path, "r.jsonl", SETS[5])])))


# ---------------------------------------------------------------- planted bad input
def test_bad_json_line_names_the_line(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text(json.dumps(rec()) + "\n{not json\n")
    with pytest.raises(SystemExit, match="line 2 is not JSON"):
        fh.load([str(p)])


def test_record_without_status_and_non_object(tmp_path):
    for body in ('{"code": "A"}\n', "[1, 2]\n", "5\n"):
        p = tmp_path / "x.jsonl"
        p.write_text(body)
        with pytest.raises(SystemExit, match="no status"):
            fh.load([str(p)])


def test_empty_file_empty_folder_missing_file(tmp_path):
    (tmp_path / "e.jsonl").write_text("\n\n")
    with pytest.raises(SystemExit, match="no records"):
        fh.load([str(tmp_path / "e.jsonl")])
    (tmp_path / "d").mkdir()
    with pytest.raises(SystemExit, match="no .jsonl"):
        fh.load([str(tmp_path / "d")])
    with pytest.raises(SystemExit):
        fh.load([str(tmp_path / "missing.jsonl")])


def test_main_prints(tmp_path, capsys):
    assert fh.main([put(tmp_path, "r.jsonl", SETS[1])]) == 0
    assert "MINION_INVENTED" in capsys.readouterr().out
