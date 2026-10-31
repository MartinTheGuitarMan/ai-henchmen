"""compare_digest: journal lines from a paired comparison. Plain code; expected text worked out by hand."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import compare_digest as cd  # noqa: E402
import trial_compare as tc  # noqa: E402

HEAD = "| tool | model | old | new | change | better | worse | worse cases |\n|---|---|---|---|---|---|---|---|"


def make(tmp_path, name, spec):
    """spec: {(tool, model): {case: [status, ...]}}; a status 'check_failed:CODE' sets the code."""
    recs = []
    for (tool, model), cases in spec.items():
        for case, sts in cases.items():
            for st in sts:
                code = st.split(":")[1] if ":" in st else None
                recs.append({"tool": tool, "model": model, "case": case, "status": st.split(":")[0], "code": code})
    p = tmp_path / f"{name}.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in recs))
    return str(p)


def lines(tmp_path, old, new, **kw):
    o = tc.per_case(tc.load(make(tmp_path, "old", old)), kw.get("model"), kw.get("tool"))
    n = tc.per_case(tc.load(make(tmp_path, "new", new)), kw.get("model"), kw.get("tool"))
    return cd.render(cd.digest(o, n)).split("\n")[2:]


T = ("t", "m")
CASES = [   # (old, new, expected lines)
    ({T: {"c1": ["ok", "ok"]}}, {T: {"c1": ["ok", "ok"]}}, ["| t | m | 2/2 (100%) | 2/2 (100%) | +0.0 pts | 0 | 0 | - |"]),
    ({T: {"c1": ["wrong", "wrong"], "c2": ["ok", "ok"]}}, {T: {"c1": ["ok", "ok"], "c2": ["ok", "ok"]}},
     ["| t | m | 2/4 (50%) | 4/4 (100%) | +50.0 pts | 1 | 0 | - |"]),
    ({T: {"c1": ["ok", "ok"], "c2": ["ok", "ok"]}}, {T: {"c1": ["wrong", "wrong"], "c2": ["ok", "ok"]}},
     ["| t | m | 4/4 (100%) | 2/4 (50%) | -50.0 pts | 0 | 1 | c1 |"]),
    ({T: {"c1": ["ok"], "c2": ["ok"]}}, {T: {"c1": ["ok"]}}, ["| t | m | 2/2 (100%) | 1/1 (100%) | +0.0 pts | 0 | 0 | - |"]),
    ({T: {"c1": ["ok"]}}, {T: {"c1": ["ok"]}, ("t", "n"): {"c1": ["ok", "wrong"]}},
     ["| t | m | 1/1 (100%) | 1/1 (100%) | +0.0 pts | 0 | 0 | - |", "| t | n | - | 1/2 (50%) | - | 0 | 0 | - |"]),
    ({T: {"c1": ["not_run"]}}, {T: {"c1": ["ok"]}}, ["| t | m | - | 1/1 (100%) | - | 0 | 0 | - |"]),
    ({T: {"c1": ["wrong", "wrong"]}}, {T: {"c1": ["check_failed:MINION_INVENTED", "check_failed:MINION_INVENTED"]}},
     ["| t | m | 0/2 (0%) | 0/2 (0%) | +0.0 pts | 0 | 0 | - |"]),
    ({T: {"c1": ["ok"], "c2": ["wrong"], "c3": ["wrong"]}}, {T: {"c1": ["wrong"], "c2": ["ok"], "c3": ["wrong"]}},
     ["| t | m | 1/3 (33%) | 1/3 (33%) | +0.0 pts | 1 | 1 | c1 |"]),
    ({T: {"c1": ["wrong"], "c2": ["wrong"], "c3": ["wrong"]}}, {T: {"c1": ["ok"], "c2": ["ok"], "c3": ["wrong"]}},
     ["| t | m | 0/3 (0%) | 2/3 (67%) | +66.7 pts | 2 | 0 | - |"]),
    ({T: {"c1": ["ok"], "c2": ["wrong"], "c3": ["wrong"]}}, {T: {"c1": ["ok"], "c2": ["ok"], "c3": ["ok"]}},
     ["| t | m | 1/3 (33%) | 3/3 (100%) | +66.7 pts | 2 | 0 | - |"]),
    ({T: {"c3": ["ok"], "c1": ["ok"], "c2": ["ok"]}}, {T: {"c1": ["wrong"], "c2": ["ok"], "c3": ["wrong"]}},
     ["| t | m | 3/3 (100%) | 1/3 (33%) | -66.7 pts | 0 | 2 | c1, c3 |"]),
    ({("b", "m"): {"c": ["ok"]}, ("a", "z"): {"c": ["ok"]}, ("a", "m"): {"c": ["wrong"]}},
     {("b", "m"): {"c": ["ok"]}, ("a", "z"): {"c": ["wrong"]}, ("a", "m"): {"c": ["ok"]}},
     ["| a | m | 0/1 (0%) | 1/1 (100%) | +100.0 pts | 1 | 0 | - |", "| a | z | 1/1 (100%) | 0/1 (0%) | -100.0 pts | 0 | 1 | c |",
      "| b | m | 1/1 (100%) | 1/1 (100%) | +0.0 pts | 0 | 0 | - |"]),
]


@pytest.mark.parametrize("old,new,expected", CASES)
def test_lines_equal_the_hand_worked_text(tmp_path, old, new, expected):
    assert lines(tmp_path, old, new) == expected


def test_filter_by_tool(tmp_path):
    old = {("a", "m"): {"c": ["ok"]}, ("b", "m"): {"c": ["ok"]}}
    new = {("a", "m"): {"c": ["wrong"]}, ("b", "m"): {"c": ["ok"]}}
    assert lines(tmp_path, old, new, tool="b") == ["| b | m | 1/1 (100%) | 1/1 (100%) | +0.0 pts | 0 | 0 | - |"]


def test_every_number_is_recomputed_from_the_raw_records(tmp_path):
    old = {T: {f"c{i}": ["ok" if i % 3 else "wrong"] * 2 for i in range(10)}}
    new = {T: {f"c{i}": ["ok" if i % 4 else "wrong"] * 2 for i in range(10)}}
    row = lines(tmp_path, old, new)[0].split("|")
    o_ok = sum(2 for i in range(10) if i % 3)
    n_ok = sum(2 for i in range(10) if i % 4)
    assert f"{o_ok}/20 ({round(100 * o_ok / 20)}%)" in row[3] and f"{n_ok}/20 ({round(100 * n_ok / 20)}%)" in row[4]
    assert f"{100 * n_ok / 20 - 100 * o_ok / 20:+.1f} pts" in row[5]
    worse = [f"c{i}" for i in range(10) if (i % 3) and not (i % 4)]
    assert row[8].strip() == ", ".join(worse)


def test_adds_what_trial_compare_lacks(tmp_path):
    old, new = {T: {"c1": ["ok"]}}, {T: {"c1": ["wrong"]}}
    text = tc.render(tc.compare(tc.per_case(tc.load(make(tmp_path, "o", old))), tc.per_case(tc.load(make(tmp_path, "n", new)))), set(), set())
    assert "pts" not in text and "%" not in text   # trial_compare prints neither rates nor changes
    assert "-100.0 pts" in lines(tmp_path, old, new)[0]


def test_planted_bad_input(tmp_path):
    good = make(tmp_path, "g", {T: {"c": ["ok"]}})
    bad = tmp_path / "bad.jsonl"
    bad.write_text("{oops\n")
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    with pytest.raises(SystemExit):
        tc.load(str(bad))
    with pytest.raises(SystemExit, match="no records"):
        cd.load(str(empty))
    with pytest.raises(SystemExit):
        cd.main([good, str(tmp_path / "missing.jsonl")])


def test_main_prints_a_table(tmp_path, capsys):
    a, b = make(tmp_path, "a", {T: {"c": ["ok"]}}), make(tmp_path, "b", {T: {"c": ["wrong"]}})
    assert cd.main([a, b, "--label", "claims fix"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("| claims fix: tool |") and "-100.0 pts" in out
