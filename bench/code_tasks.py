"""Coding bench tasks: 17 invented Python tasks with hidden pytest tests.

Every task has a prompt (what the model sees), hidden tests (what scores it; the model never sees them), and a
reference solution used only by the unit tests to prove the tests are right (a correct solution passes all of them;
for bug-fix tasks the buggy code shown to the model fails some). Everything here is invented and public.

kinds: write (a small function or class), fix (given code with a bug described in words), regex (a compiled PATTERN).
levels: easy, medium, hard.
"""
from __future__ import annotations

import re

FENCE_RULE = ("Standard library only. Reply with exactly one fenced ```python block that contains the complete module, "
              "and no explanation outside the block.")

TASKS: list[dict] = []


def task(id: str, kind: str, level: str, prompt: str, tests: str, reference: str, buggy: str | None = None) -> None:
    body = prompt.strip()
    if kind == "fix" and "```python" not in body:
        body += f"\n\n```python\n{buggy.strip()}\n```"
    TASKS.append({"id": id, "kind": kind, "level": level, "prompt": body + "\n\n" + FENCE_RULE,
                  "tests": tests.strip() + "\n", "reference": reference.strip() + "\n",
                  "buggy": buggy.strip() + "\n" if buggy else None,
                  "n_tests": len(re.findall(r"^def test_", tests, re.M))})


# ---------------------------------------------------------------- write tasks
task("merge_intervals", "write", "medium", """
Write a function `merge_intervals(intervals)` that takes a list of `(start, end)` integer tuples (with start <= end)
in any order and returns a new sorted list of tuples in which all intervals that overlap or touch (an interval ending
at 5 and one starting at 5 touch) are merged into one. The input list must not be modified. An empty list gives an
empty list.
""", """
from solution import merge_intervals

def test_basic():
    assert merge_intervals([(1, 3), (2, 6), (8, 10)]) == [(1, 6), (8, 10)]

def test_unsorted():
    assert merge_intervals([(8, 10), (1, 3), (2, 6)]) == [(1, 6), (8, 10)]

def test_touching_merge():
    assert merge_intervals([(1, 5), (5, 8)]) == [(1, 8)]

def test_adjacent_but_apart():
    assert merge_intervals([(1, 4), (5, 8)]) == [(1, 4), (5, 8)]

def test_contained():
    assert merge_intervals([(1, 10), (2, 3), (4, 5)]) == [(1, 10)]

def test_empty_and_single():
    assert merge_intervals([]) == []
    assert merge_intervals([(4, 4)]) == [(4, 4)]

def test_input_not_modified():
    data = [(5, 6), (1, 2), (2, 3)]
    copy = list(data)
    merge_intervals(data)
    assert data == copy

def test_returns_tuples_negative():
    out = merge_intervals([(-5, -1), (-2, 2)])
    assert out == [(-5, 2)]
    assert all(isinstance(x, tuple) for x in out)
""", """
def merge_intervals(intervals):
    out = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out
""")

task("parse_duration", "write", "medium", """
Write a function `parse_duration(text)` that converts a duration string into a whole number of seconds. The string is
one or more `<integer><unit>` parts with no spaces, where the unit is `d` (86400 s), `h` (3600 s), `m` (60 s) or
`s` (1 s). Units must appear in that order (days, hours, minutes, seconds) and each at most once, for example
`"1h30m"`, `"2d"`, `"1d2h3m4s"`, `"0s"`. Anything else raises `ValueError`: an empty string, a number without a unit
(`"90"`), a repeated or out-of-order unit (`"1h1h"`, `"30m1h"`), decimals (`"1.5h"`), spaces, negative numbers,
unknown units.
""", """
import pytest
from solution import parse_duration

def test_single_units():
    assert parse_duration("45s") == 45
    assert parse_duration("2m") == 120
    assert parse_duration("3h") == 10800
    assert parse_duration("2d") == 172800

def test_combined():
    assert parse_duration("1h30m") == 5400
    assert parse_duration("1d2h3m4s") == 93784

def test_zero():
    assert parse_duration("0s") == 0
    assert parse_duration("0d0h") == 0

def test_big_numbers():
    assert parse_duration("100m") == 6000

def test_invalid_missing_or_unknown_unit():
    for bad in ["", "90", "h", "s1", "5x"]:
        with pytest.raises(ValueError):
            parse_duration(bad)

def test_invalid_order_or_repeat():
    for bad in ["1h1h", "30m1h", "1s1m"]:
        with pytest.raises(ValueError):
            parse_duration(bad)

def test_invalid_syntax():
    for bad in ["1.5h", "1 h", "-5s", "1h 30m", "+5s"]:
        with pytest.raises(ValueError):
            parse_duration(bad)

def test_returns_int():
    assert type(parse_duration("1m")) is int
""", """
import re

def parse_duration(text):
    m = re.fullmatch(r"(?:([0-9]+)d)?(?:([0-9]+)h)?(?:([0-9]+)m)?(?:([0-9]+)s)?", text)
    if not m or not text:
        raise ValueError(text)
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s
""")

task("slugify", "write", "easy", """
Write a function `slugify(text)` that turns a title into a URL slug: accented letters are reduced to their plain ASCII
letter (`é` becomes `e`), everything is lower case, every run of characters that are not ASCII letters or digits
(spaces, punctuation, underscores, symbols, characters from other scripts) becomes a single `-`, and leading and
trailing `-` are removed. If nothing is left the result is an empty string.
""", """
from solution import slugify

def test_basic():
    assert slugify("Hello, World!") == "hello-world"

def test_accents():
    assert slugify("Crème Brûlée recipe") == "creme-brulee-recipe"

def test_runs_and_edges():
    assert slugify("  --a__b--  ") == "a-b"

def test_symbols():
    assert slugify("C++ & Rust") == "c-rust"

def test_empty_results():
    assert slugify("") == ""
    assert slugify("!!!") == ""

def test_other_script_dropped():
    assert slugify("Ünïcode 日本 ok") == "unicode-ok"

def test_digits_kept():
    assert slugify("Top 10 of 2024") == "top-10-of-2024"
""", """
import re
import unicodedata

def slugify(text):
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")
""")

task("business_days", "write", "medium", """
Write a function `business_days(start, end)` that takes two `datetime.date` objects and returns how many days from
`start` (included) up to `end` (excluded) are weekdays, Monday to Friday. There are no holidays. If `end` is on or
before `start`, return 0.
""", """
from datetime import date
from solution import business_days

def test_one_full_week():
    assert business_days(date(2024, 1, 1), date(2024, 1, 8)) == 5

def test_friday_to_monday():
    assert business_days(date(2024, 1, 5), date(2024, 1, 8)) == 1

def test_weekend_only():
    assert business_days(date(2024, 1, 6), date(2024, 1, 8)) == 0

def test_same_day_and_reversed():
    assert business_days(date(2024, 1, 3), date(2024, 1, 3)) == 0
    assert business_days(date(2024, 1, 10), date(2024, 1, 3)) == 0

def test_end_excluded_start_included():
    assert business_days(date(2024, 1, 3), date(2024, 1, 4)) == 1

def test_whole_leap_year():
    assert business_days(date(2024, 1, 1), date(2025, 1, 1)) == 262

def test_partial_weeks():
    assert business_days(date(2024, 3, 7), date(2024, 3, 20)) == 9
""", """
from datetime import timedelta

def business_days(start, end):
    n, d = 0, start
    while d < end:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n
""")

task("parse_csv_line", "write", "medium", """
Write a function `parse_csv_line(line)` that splits one line of CSV text into a list of field strings. Fields are
separated by commas. A field may be wrapped in double quotes; inside a quoted field commas are literal and a doubled
double quote (`""`) stands for one double quote. Unquoted fields are returned exactly as written (spaces are kept).
An empty line gives `[""]`, and a trailing comma gives a trailing empty field. A quote that is never closed raises
`ValueError`. The line contains no newlines.
""", """
import pytest
from solution import parse_csv_line

def test_plain():
    assert parse_csv_line("a,b,c") == ["a", "b", "c"]

def test_quoted_comma():
    assert parse_csv_line('a,"b,c",d') == ["a", "b,c", "d"]

def test_escaped_quote():
    assert parse_csv_line('"say ""hi"" now",x') == ['say "hi" now', "x"]

def test_empty_fields():
    assert parse_csv_line("") == [""]
    assert parse_csv_line("a,,b,") == ["a", "", "b", ""]
    assert parse_csv_line(',') == ["", ""]

def test_spaces_kept():
    assert parse_csv_line(" a , b ") == [" a ", " b "]

def test_quoted_empty():
    assert parse_csv_line('"",x') == ["", "x"]

def test_unterminated_quote():
    with pytest.raises(ValueError):
        parse_csv_line('a,"b')

def test_quote_only_field_with_escape_at_end():
    assert parse_csv_line('"a"' + '""') == ['a"']
""", """
def parse_csv_line(line):
    out, i, n = [], 0, len(line)
    while True:
        if i < n and line[i] == '"':
            i += 1
            buf = []
            while True:
                if i >= n:
                    raise ValueError("unterminated quote")
                if line[i] == '"':
                    if i + 1 < n and line[i + 1] == '"':
                        buf.append('"')
                        i += 2
                        continue
                    i += 1
                    break
                buf.append(line[i])
                i += 1
            out.append("".join(buf))
        else:
            j = line.find(",", i)
            j = n if j < 0 else j
            out.append(line[i:j])
            i = j
        if i >= n:
            return out
        if line[i] != ",":
            raise ValueError("text after closing quote")
        i += 1
        if i >= n:
            out.append("")
            return out
""")

task("wrap_text", "write", "medium", """
Write a function `wrap_text(text, width)` that wraps text greedily and returns a list of lines. Words are the pieces
you get by splitting on any whitespace; lines join words with a single space; a line may not be longer than `width`
characters unless it consists of one single word that is itself longer than `width` (such a word stays whole on its
own line). Each line takes as many words as fit. No line has leading or trailing spaces. Empty or whitespace-only text
gives an empty list.
""", """
from solution import wrap_text

def test_basic():
    assert wrap_text("the quick brown fox jumps", 10) == ["the quick", "brown fox", "jumps"]

def test_exact_fit():
    assert wrap_text("aa bb cc", 5) == ["aa bb", "cc"]

def test_long_word_alone():
    assert wrap_text("a extraordinarily b", 5) == ["a", "extraordinarily", "b"]

def test_whitespace_collapsed():
    assert wrap_text("  one \\n two\\tthree  ", 7) == ["one two", "three"]

def test_empty():
    assert wrap_text("", 10) == []
    assert wrap_text("   \\n ", 10) == []

def test_width_one():
    assert wrap_text("a b c", 1) == ["a", "b", "c"]

def test_all_fits_one_line():
    assert wrap_text("short text", 80) == ["short text"]

def test_no_line_exceeds_width():
    text = "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod"
    for line in wrap_text(text, 12):
        assert len(line) <= 12
""", """
def wrap_text(text, width):
    lines, cur = [], ""
    for w in text.split():
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines
""")

task("compare_versions", "write", "hard", """
Write a function `compare_versions(a, b)` that compares two version strings by Semantic Versioning precedence and
returns -1 if `a` is lower than `b`, 0 if equal, 1 if higher. Format: `MAJOR.MINOR.PATCH`, optionally followed by
`-` and a dot-separated pre-release (for example `1.0.0-alpha.1`), optionally followed by `+` and build metadata
(which is ignored completely). Rules: compare major, minor and patch as integers. A version with a pre-release is
lower than the same version without one. Two pre-releases are compared identifier by identifier, left to right:
identifiers made only of digits compare as integers, others compare as ASCII text, a numeric identifier is lower than
a text one, and if all shared identifiers are equal the one with fewer identifiers is lower. Examples of the correct
order: 1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta < 1.0.0-beta < 1.0.0-beta.2 < 1.0.0-beta.11 < 1.0.0-rc.1 <
1.0.0. You may assume inputs are well formed.
""", """
from solution import compare_versions

ORDER = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2",
         "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"]

def test_core_numeric():
    assert compare_versions("1.10.0", "1.9.0") == 1
    assert compare_versions("1.2.3", "1.2.4") == -1
    assert compare_versions("2.0.0", "10.0.0") == -1

def test_equal():
    assert compare_versions("1.2.3", "1.2.3") == 0

def test_prerelease_lower_than_release():
    assert compare_versions("1.0.0-rc.1", "1.0.0") == -1
    assert compare_versions("1.0.0", "1.0.0-rc.1") == 1

def test_semver_spec_chain():
    for i in range(len(ORDER) - 1):
        assert compare_versions(ORDER[i], ORDER[i + 1]) == -1
        assert compare_versions(ORDER[i + 1], ORDER[i]) == 1

def test_numeric_vs_text_identifier():
    assert compare_versions("1.0.0-1", "1.0.0-a") == -1
    assert compare_versions("1.0.0-alpha.2", "1.0.0-alpha.10") == -1

def test_build_metadata_ignored():
    assert compare_versions("1.0.0+a", "1.0.0+b") == 0
    assert compare_versions("1.0.0-rc.1+x", "1.0.0-rc.1") == 0

def test_text_compared_as_ascii():
    assert compare_versions("1.0.0-Beta", "1.0.0-alpha") == -1
""", """
def _key(v):
    v = v.split("+", 1)[0]
    core, _, pre = v.partition("-")
    nums = tuple(int(x) for x in core.split("."))
    return nums, pre

def _cmp(x, y):
    return (x > y) - (x < y)

def compare_versions(a, b):
    (na, pa), (nb, pb) = _key(a), _key(b)
    if na != nb:
        return _cmp(na, nb)
    if pa == pb:
        return 0
    if not pa:
        return 1
    if not pb:
        return -1
    ia, ib = pa.split("."), pb.split(".")
    for x, y in zip(ia, ib):
        if x == y:
            continue
        xd, yd = x.isdigit(), y.isdigit()
        if xd and yd:
            return _cmp(int(x), int(y))
        if xd:
            return -1
        if yd:
            return 1
        return _cmp(x, y)
    return _cmp(len(ia), len(ib))
""")

task("toposort", "write", "hard", """
Write a function `toposort(deps)`. `deps` is a dict that maps a name to a list of names it depends on, for example
`{"app": ["lib", "util"], "lib": ["util"]}`. Return a list of all names, including names that only appear inside
dependency lists, such that every name comes after everything it depends on. When several names are ready at the same
time, choose the alphabetically smallest first, so the result is unique. If the dependencies contain a cycle
(including a name that depends on itself), raise `ValueError`. The input must not be modified.
""", """
import pytest
from solution import toposort

def test_chain():
    assert toposort({"app": ["lib", "util"], "lib": ["util"]}) == ["util", "lib", "app"]

def test_names_only_in_lists():
    assert toposort({"a": ["z"]}) == ["z", "a"]

def test_alphabetical_tie_break():
    assert toposort({"c": [], "a": [], "b": []}) == ["a", "b", "c"]

def test_tie_break_with_dependencies():
    deps = {"d": ["b", "c"], "c": ["a"], "b": ["a"], "a": [], "e": []}
    assert toposort(deps) == ["a", "b", "c", "d", "e"]

def test_late_small_name_goes_first_when_ready():
    # "a" depends on "z", so "b" is ready before "a" is, but once "z" is placed "a" is the smallest ready name
    assert toposort({"a": ["z"], "b": []}) == ["b", "z", "a"]

def test_empty():
    assert toposort({}) == []

def test_cycle():
    with pytest.raises(ValueError):
        toposort({"a": ["b"], "b": ["c"], "c": ["a"]})

def test_self_cycle():
    with pytest.raises(ValueError):
        toposort({"a": ["a"]})

def test_input_not_modified():
    deps = {"a": ["b"], "b": []}
    toposort(deps)
    assert deps == {"a": ["b"], "b": []}

def test_duplicate_dependency_entries():
    assert toposort({"a": ["b", "b"], "b": []}) == ["b", "a"]
""", """
import heapq

def toposort(deps):
    names = set(deps)
    for v in deps.values():
        names.update(v)
    waiting = {n: set(deps.get(n, ())) for n in names}
    users = {n: [] for n in names}
    for n, ds in waiting.items():
        for d in ds:
            users[d].append(n)
    ready = [n for n, ds in waiting.items() if not ds]
    heapq.heapify(ready)
    out = []
    while ready:
        n = heapq.heappop(ready)
        out.append(n)
        for u in users[n]:
            waiting[u].discard(n)
            if not waiting[u]:
                heapq.heappush(ready, u)
    if len(out) != len(names):
        raise ValueError("cycle")
    return out
""")

task("lru_cache", "write", "medium", """
Write a class `LRUCache` with `__init__(self, capacity)`, `get(self, key)`, `put(self, key, value)`, `__len__(self)`
and `keys(self)`. It holds at most `capacity` entries. `get` returns the value, or `None` if the key is missing, and
marks the key as most recently used. `put` inserts or updates a key (an update also marks it most recently used); if
the cache is then over capacity, the least recently used entry is dropped. `keys()` returns a list of the keys from
least recently used to most recently used. A capacity below 1 raises `ValueError`.
""", """
import pytest
from solution import LRUCache

def test_basic_eviction():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("c", 3)
    assert c.get("a") is None
    assert c.get("b") == 2
    assert c.get("c") == 3
    assert len(c) == 2

def test_get_refreshes():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") == 1
    c.put("c", 3)
    assert c.get("b") is None
    assert c.get("a") == 1

def test_update_refreshes_and_replaces():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("a", 10)
    c.put("c", 3)
    assert c.get("a") == 10
    assert c.get("b") is None

def test_keys_order():
    c = LRUCache(3)
    for k in "abc":
        c.put(k, k)
    c.get("a")
    assert c.keys() == ["b", "c", "a"]

def test_update_does_not_grow():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("a", 2)
    assert len(c) == 1

def test_capacity_one():
    c = LRUCache(1)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") is None and c.get("b") == 2

def test_bad_capacity():
    with pytest.raises(ValueError):
        LRUCache(0)
    with pytest.raises(ValueError):
        LRUCache(-3)

def test_falsy_values_are_values():
    c = LRUCache(2)
    c.put("z", 0)
    assert c.get("z") == 0
    assert len(c) == 1
""", """
from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity):
        if capacity < 1:
            raise ValueError("capacity")
        self.capacity = capacity
        self._d = OrderedDict()

    def get(self, key):
        if key not in self._d:
            return None
        self._d.move_to_end(key)
        return self._d[key]

    def put(self, key, value):
        self._d[key] = value
        self._d.move_to_end(key)
        if len(self._d) > self.capacity:
            self._d.popitem(last=False)

    def __len__(self):
        return len(self._d)

    def keys(self):
        return list(self._d)
""")

task("flatten_dict", "write", "easy", """
Write a function `flatten_dict(d, sep=".")` that flattens a nested dictionary into a single-level dictionary. The key
of a nested value is the path of keys joined with `sep`, for example `{"a": {"b": 1}}` becomes `{"a.b": 1}`. Only
dictionaries are descended into; lists and other values are kept as they are. An empty nested dictionary is kept as
an empty dictionary under its key. All keys are strings. The input must not be modified.
""", """
from solution import flatten_dict

def test_basic():
    assert flatten_dict({"a": {"b": 1, "c": {"d": 2}}, "e": 3}) == {"a.b": 1, "a.c.d": 2, "e": 3}

def test_custom_sep():
    assert flatten_dict({"a": {"b": 1}}, sep="/") == {"a/b": 1}

def test_lists_kept():
    assert flatten_dict({"a": {"b": [1, {"c": 2}]}}) == {"a.b": [1, {"c": 2}]}

def test_empty_nested_dict_kept():
    assert flatten_dict({"a": {}, "b": {"c": {}}}) == {"a": {}, "b.c": {}}

def test_empty_input():
    assert flatten_dict({}) == {}

def test_input_not_modified():
    d = {"a": {"b": 1}}
    flatten_dict(d)
    assert d == {"a": {"b": 1}}
""", """
def flatten_dict(d, sep="."):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict) and v:
            for k2, v2 in flatten_dict(v, sep).items():
                out[k + sep + k2] = v2
        else:
            out[k] = v
    return out
""")

# ---------------------------------------------------------------- fix tasks
task("fix_median", "fix", "easy", """
The function `median` below is supposed to return the median of a list of numbers: the middle value for an odd
number of values, and the average of the two middle values for an even number. It must not modify its argument and
must raise `ValueError` for an empty list. Currently `median([1, 2, 3, 4])` returns 3 but should return 2.5, and
`median([])` raises `IndexError` instead of `ValueError`. Fix it and return the complete corrected module.
""", """
import pytest
from solution import median

def test_odd():
    assert median([3, 1, 2]) == 2

def test_even():
    assert median([1, 2, 3, 4]) == 2.5
    assert median([4, 1]) == 2.5

def test_single():
    assert median([7]) == 7

def test_empty():
    with pytest.raises(ValueError):
        median([])

def test_not_modified():
    data = [3, 1, 2]
    median(data)
    assert data == [3, 1, 2]

def test_floats_and_negatives():
    assert median([-1.5, 0, 2.5, 10]) == 1.25
""", """
def median(values):
    if not values:
        raise ValueError("empty")
    s = sorted(values)
    n = len(s)
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2
""", buggy="""
def median(values):
    s = sorted(values)
    n = len(s)
    return s[n // 2]
""")

task("fix_chunked", "fix", "easy", """
The function `chunked` below should split a list into consecutive chunks of `size` items; the last chunk may be
shorter. `chunked([1, 2, 3, 4, 5], 2)` should return `[[1, 2], [3, 4], [5]]` but returns `[[1, 2], [3, 4]]`, so the
last partial chunk is lost. A `size` below 1 should raise `ValueError`. Fix it and return the complete corrected
module.
""", """
import pytest
from solution import chunked

def test_remainder_kept():
    assert chunked([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]

def test_exact():
    assert chunked([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]

def test_size_larger_than_list():
    assert chunked([1, 2], 5) == [[1, 2]]

def test_empty():
    assert chunked([], 3) == []

def test_size_one():
    assert chunked("abc", 1) == [["a"], ["b"], ["c"]]

def test_bad_size():
    with pytest.raises(ValueError):
        chunked([1], 0)
""", """
def chunked(items, size):
    if size < 1:
        raise ValueError("size")
    return [list(items[i:i + size]) for i in range(0, len(items), size)]
""", buggy="""
def chunked(items, size):
    return [list(items[i:i + size]) for i in range(0, len(items) - size + 1, size)]
""")

task("fix_unique_bucket", "fix", "easy", """
The function `append_unique` below should add `item` to the list `bucket` unless it is already in it, and return the
list. When no `bucket` is passed, every call must start with a fresh empty list. Currently two separate calls
without a bucket share state: `append_unique("a")` then `append_unique("b")` returns `["a", "b"]` for the second call
but should return `["b"]`. Fix it and return the complete corrected module.
""", """
from solution import append_unique

def test_fresh_list_each_call():
    assert append_unique("a") == ["a"]
    assert append_unique("b") == ["b"]

def test_explicit_bucket_is_used():
    b = ["x"]
    out = append_unique("y", b)
    assert out == ["x", "y"]
    assert b == ["x", "y"]

def test_no_duplicates():
    b = ["x"]
    assert append_unique("x", b) == ["x"]

def test_many_calls_independent():
    for i in range(5):
        assert append_unique(i) == [i]
""", """
def append_unique(item, bucket=None):
    if bucket is None:
        bucket = []
    if item not in bucket:
        bucket.append(item)
    return bucket
""", buggy="""
def append_unique(item, bucket=[]):
    if item not in bucket:
        bucket.append(item)
    return bucket
""")

task("fix_top_words", "fix", "medium", """
The function `top_words` below should return the `n` most frequent words of a text as a list of lowercase words.
Words are separated by whitespace, comparison ignores case, and the punctuation characters `.,;:!?` at the start or
end of a word are ignored. Words with the same count are ordered alphabetically. Currently
`top_words("The cat and the dog and THE bird", 2)` returns `['The', 'and']` but should return `['the', 'and']`, and
`top_words("Hi! hi, hi. yo", 1)` returns `['yo']` or similar instead of `['hi']`. Fix it and return the complete
corrected module.
""", """
from solution import top_words

def test_case_insensitive():
    assert top_words("The cat and the dog and THE bird", 2) == ["the", "and"]

def test_punctuation_stripped():
    assert top_words("Hi! hi, hi. yo", 1) == ["hi"]

def test_tie_break_alphabetical():
    assert top_words("pear apple pear apple fig", 3) == ["apple", "pear", "fig"]

def test_n_larger_than_vocabulary():
    assert top_words("a b a", 10) == ["a", "b"]

def test_empty_and_zero():
    assert top_words("", 3) == []
    assert top_words("a b", 0) == []

def test_punctuation_only_tokens_ignored():
    assert top_words("a ... a !!! b", 2) == ["a", "b"]

def test_inner_punctuation_kept():
    assert top_words("don't don't stop", 1) == ["don't"]
""", """
def top_words(text, n):
    counts = {}
    for w in text.split():
        w = w.strip(".,;:!?").lower()
        if w:
            counts[w] = counts.get(w, 0) + 1
    ranked = sorted(counts, key=lambda w: (-counts[w], w))
    return ranked[:n]
""", buggy="""
def top_words(text, n):
    counts = {}
    for w in text.split():
        counts[w] = counts.get(w, 0) + 1
    return sorted(counts, key=counts.get, reverse=True)[:n]
""")

# ---------------------------------------------------------------- regex tasks
task("re_hex_color", "regex", "easy", """
Define a module-level compiled regular expression `PATTERN` (made with `re.compile`) that matches CSS hex colors:
a `#` followed by exactly 3 or exactly 6 hexadecimal digits (0-9, a-f, A-F, either case). The tests use
`PATTERN.fullmatch(text)`, so the whole string must be a color: `"#fff"` and `"#A1b2C3"` match; `"#ffff"`, `"fff"`,
`"#ggg"`, `"#12345"` and `"#fffffff"` do not.
""", """
import re
from solution import PATTERN

GOOD = ["#fff", "#FFF", "#a1B", "#000000", "#A1b2C3", "#0f0f0f"]
BAD = ["", "#", "fff", "#ff", "#ffff", "#12345", "#fffffff", "#ggg", "#12 345", " #fff", "#fff ", "##fff", "#ffg000"]

def test_is_compiled():
    assert isinstance(PATTERN, re.Pattern)

def test_good():
    for s in GOOD:
        assert PATTERN.fullmatch(s), s

def test_bad():
    for s in BAD:
        assert not PATTERN.fullmatch(s), s

def test_trailing_newline_rejected():
    assert not PATTERN.fullmatch("#fff\\n")
""", """
import re
PATTERN = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")
""")

task("re_dates_in_text", "regex", "medium", """
Define a module-level compiled regular expression `PATTERN` (made with `re.compile`) that finds ISO dates in running
text. A date is `YYYY-MM-DD`: four digits, a hyphen, a month from `01` to `12`, a hyphen, a day from `01` to `31`
(no check that the day exists in that month, so `2024-02-31` counts). It must not match inside a longer run of
digits or hyphen-joined numbers: `12024-01-05` and `2024-01-055` contain no date. The tests collect results with
`[m.group(0) for m in PATTERN.finditer(text)]`, so only the date itself may be matched (do not include surrounding
characters in the match).
""", """
import re
from solution import PATTERN

def find(text):
    return [m.group(0) for m in PATTERN.finditer(text)]

def test_is_compiled():
    assert isinstance(PATTERN, re.Pattern)

def test_simple():
    assert find("Due 2024-03-15, then 2025-12-01.") == ["2024-03-15", "2025-12-01"]

def test_month_range():
    assert find("2024-00-10 2024-13-10 2024-12-10") == ["2024-12-10"]

def test_day_range():
    assert find("2024-01-00 2024-01-32 2024-01-31 2024-02-31") == ["2024-01-31", "2024-02-31"]

def test_not_inside_longer_digits():
    assert find("12024-01-05 2024-01-055 x2024-01-05") == ["2024-01-05"]

def test_adjacent_punctuation():
    assert find("(2020-05-05) [2021-06-06]; 2022-07-07!") == ["2020-05-05", "2021-06-06", "2022-07-07"]

def test_no_dates():
    assert find("version 1.2.3 on 24-01-05") == []

def test_no_capture_group_leak():
    assert find("on 1999-09-09") == ["1999-09-09"]
""", """
import re
PATTERN = re.compile(r"(?<![0-9])[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])(?![0-9])")
""")

task("re_ipv4", "regex", "hard", """
Define a module-level compiled regular expression `PATTERN` (made with `re.compile`) that matches IPv4 addresses in
dotted decimal form: exactly four numbers separated by single dots, each number written with the ASCII digits 0-9
only, with a value from 0 to 255 and no leading zeros (`0` is fine, `00` and `01` are not). The tests use
`PATTERN.fullmatch(text)`, so the whole string must be the address: `"192.168.0.1"` and `"255.255.255.255"` match;
`"256.1.1.1"`, `"1.2.3"`, `"1.2.3.4.5"`, `"01.2.3.4"`, `" 1.2.3.4"` and `"1.2.3.4\\n"` do not.
""", """
import re
from solution import PATTERN

GOOD = ["0.0.0.0", "255.255.255.255", "192.168.0.1", "10.0.0.1", "1.2.3.4", "249.250.251.199", "100.200.99.9"]
BAD = ["", "256.1.1.1", "1.256.1.1", "1.1.1.256", "300.1.1.1", "1.2.3", "1.2.3.4.5", "01.2.3.4", "1.2.3.04", "00.0.0.0",
       " 1.2.3.4", "1.2.3.4 ", "1..3.4", "1.2.3.", ".1.2.3", "a.b.c.d", "1.2.3.4a", "-1.2.3.4", "1,2,3,4", "999.999.999.999"]

def test_is_compiled():
    assert isinstance(PATTERN, re.Pattern)

def test_good():
    for s in GOOD:
        assert PATTERN.fullmatch(s), s

def test_bad():
    for s in BAD:
        assert not PATTERN.fullmatch(s), s

def test_trailing_newline_rejected():
    assert not PATTERN.fullmatch("1.2.3.4\\n")

def test_non_ascii_digits_rejected():
    assert not PATTERN.fullmatch("\\u0661.2.3.4")
    assert not PATTERN.fullmatch("\\uff11.\\uff12.\\uff13.\\uff14")
""", """
import re
OCTET = r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9][0-9]|[0-9])"
PATTERN = re.compile(rf"{OCTET}(?:\\.{OCTET}){{3}}")
""")


# ---------------------------------------------------------------- complex tier
# Longer, stateful or multi-part tasks. Same scoring and sandbox. Level "complex" is reported as its own tier.
# For the multi-module task both modules are merged into one file (the sandbox runs one solution file).

task("cx_ttl_cache", "write", "complex", r"""
Write a class `TTLCache` for a cache whose entries expire. Constructor: `TTLCache(capacity, ttl, clock=time.monotonic)`.
`capacity` must be at least 1 and `ttl` greater than 0, otherwise `ValueError`. `clock` is a function returning the
current time in seconds; the tests pass a fake one.

- `put(key, value)` stores the value; it expires `ttl` seconds after this call (a second `put` of the same key
  replaces the value and restarts the expiry). The key becomes the most recently used one.
- `get(key)` returns the value, or `None` if the key is missing or expired. An entry is expired when
  `clock() >= expiry time`. Reading does not extend the expiry, but it makes the key the most recently used one.
  An expired entry is removed when it is found.
- `__len__` counts only entries that are not expired.
- `keys()` returns the keys of entries that are not expired, from least to most recently used.
- When a `put` makes the cache hold more than `capacity` entries, expired entries are dropped first; if it is still
  over capacity, the least recently used entries are dropped until it fits.
""", r"""
import pytest
from solution import TTLCache

class Clock:
    def __init__(self):
        self.t = 0.0
    def __call__(self):
        return self.t

def make(cap=3, ttl=10):
    c = Clock()
    return TTLCache(cap, ttl, clock=c), c

def test_basic_get_put():
    cache, _ = make()
    cache.put("a", 1)
    assert cache.get("a") == 1
    assert cache.get("zz") is None

def test_expiry_boundary():
    cache, clk = make(ttl=10)
    cache.put("a", 1)
    clk.t = 9.99
    assert cache.get("a") == 1
    clk.t = 10.0
    assert cache.get("a") is None

def test_len_counts_only_live_entries():
    cache, clk = make()
    cache.put("a", 1)
    clk.t = 5
    cache.put("b", 2)
    clk.t = 12
    assert len(cache) == 1
    assert cache.keys() == ["b"]

def test_put_again_restarts_expiry():
    cache, clk = make(ttl=10)
    cache.put("a", 1)
    clk.t = 8
    cache.put("a", 2)
    clk.t = 15
    assert cache.get("a") == 2

def test_get_does_not_extend_expiry():
    cache, clk = make(ttl=10)
    cache.put("a", 1)
    clk.t = 9
    assert cache.get("a") == 1
    clk.t = 10
    assert cache.get("a") is None

def test_lru_eviction_when_full():
    cache, _ = make(cap=2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")
    cache.put("c", 3)
    assert cache.get("b") is None
    assert cache.keys() == ["a", "c"]

def test_expired_entries_dropped_before_live_lru():
    cache, clk = make(cap=2, ttl=10)
    cache.put("old", 1)
    clk.t = 6
    cache.put("live", 2)
    clk.t = 11          # "old" expired, "live" alive
    cache.get("live")
    cache.put("new", 3)
    assert cache.get("live") == 2 and cache.get("new") == 3

def test_keys_order_is_recency():
    cache, _ = make(cap=3)
    for k in "abc":
        cache.put(k, k)
    cache.get("a")
    cache.put("b", "B")
    assert cache.keys() == ["c", "a", "b"]

def test_bad_arguments():
    with pytest.raises(ValueError):
        TTLCache(0, 5)
    with pytest.raises(ValueError):
        TTLCache(2, 0)
    with pytest.raises(ValueError):
        TTLCache(2, -1)

def test_falsy_value_is_stored():
    cache, _ = make()
    cache.put("z", 0)
    assert cache.get("z") == 0 and len(cache) == 1
""", r"""
import time
from collections import OrderedDict

class TTLCache:
    def __init__(self, capacity, ttl, clock=time.monotonic):
        if capacity < 1 or ttl <= 0:
            raise ValueError("bad arguments")
        self.capacity, self.ttl, self.clock = capacity, ttl, clock
        self._d = OrderedDict()   # key -> (value, expires_at)

    def _purge(self):
        now = self.clock()
        for k in [k for k, (_, e) in self._d.items() if now >= e]:
            del self._d[k]

    def put(self, key, value):
        self._d[key] = (value, self.clock() + self.ttl)
        self._d.move_to_end(key)
        if len(self._d) > self.capacity:
            self._purge()
        while len(self._d) > self.capacity:
            self._d.popitem(last=False)

    def get(self, key):
        item = self._d.get(key)
        if item is None:
            return None
        if self.clock() >= item[1]:
            del self._d[key]
            return None
        self._d.move_to_end(key)
        return item[0]

    def __len__(self):
        self._purge()
        return len(self._d)

    def keys(self):
        self._purge()
        return list(self._d)
""")

task("cx_scheduler", "write", "complex", r"""
Write a class `Scheduler` that runs callbacks at given times. Time is passed in by the caller as plain numbers.

- `schedule(name, run_at, callback, every=None)`: add a task. `name` is unique among pending tasks, otherwise
  `ValueError`. `callback` takes no arguments. If `every` is given it must be greater than 0 (else `ValueError`) and
  the task repeats.
- `cancel(name)`: remove a pending task; return `True` if it existed, `False` otherwise.
- `pending()`: list of `(run_at, name)` for all pending tasks, sorted by `run_at` and then by the order in which the
  tasks were first scheduled.
- `run_due(now)`: run every task whose `run_at <= now`, one after the other, ordered by `run_at` and then by the order
  in which they were first scheduled, and return the list of the names that were run, in that order.
  - A one-time task is removed after it ran.
  - A repeating task runs at most once per `run_due` call. Afterwards its `run_at` moves forward in steps of `every`
    until it is greater than `now`; runs that were missed in between are skipped, not made up.
  - If a callback raises an exception, it is caught, `(name, exception)` is appended to the list `self.errors`, the task
    still counts as run (and is rescheduled or removed as above), and the other tasks continue.
  - Tasks that a callback adds during `run_due` are not run in the same call. A task cancelled by an earlier callback
    in the same call is not run.
""", r"""
import pytest
from solution import Scheduler

def collector():
    log = []
    return log, (lambda n: (lambda: log.append(n)))

def test_runs_due_tasks_in_time_then_insertion_order():
    s = Scheduler()
    log, cb = collector()
    s.schedule("late", 5, cb("late"))
    s.schedule("b", 2, cb("b"))
    s.schedule("a", 2, cb("a"))
    assert s.run_due(3) == ["b", "a"]
    assert log == ["b", "a"]
    assert [n for _, n in s.pending()] == ["late"]

def test_boundary_inclusive():
    s = Scheduler()
    log, cb = collector()
    s.schedule("x", 5, cb("x"))
    assert s.run_due(4.99) == []
    assert s.run_due(5) == ["x"]
    assert s.run_due(100) == []

def test_duplicate_name_and_bad_every():
    s = Scheduler()
    s.schedule("x", 1, lambda: None)
    with pytest.raises(ValueError):
        s.schedule("x", 2, lambda: None)
    with pytest.raises(ValueError):
        s.schedule("y", 2, lambda: None, every=0)

def test_cancel():
    s = Scheduler()
    s.schedule("x", 1, lambda: None)
    assert s.cancel("x") is True
    assert s.cancel("x") is False
    assert s.run_due(10) == []

def test_repeating_runs_once_per_call_and_skips_missed():
    s = Scheduler()
    log, cb = collector()
    s.schedule("tick", 10, cb("tick"), every=10)
    assert s.run_due(45) == ["tick"]
    assert s.pending() == [(50, "tick")]
    assert s.run_due(45) == []
    assert s.run_due(50) == ["tick"]
    assert s.pending() == [(60, "tick")]
    assert len(log) == 2

def test_repeating_exact_boundary_moves_strictly_past_now():
    s = Scheduler()
    s.schedule("t", 0, lambda: None, every=5)
    s.run_due(10)
    assert s.pending() == [(15, "t")]

def test_exception_is_recorded_and_others_continue():
    s = Scheduler()
    log, cb = collector()
    def boom():
        raise RuntimeError("bad")
    s.schedule("boom", 1, boom)
    s.schedule("ok", 2, cb("ok"))
    assert s.run_due(5) == ["boom", "ok"]
    assert log == ["ok"]
    assert len(s.errors) == 1 and s.errors[0][0] == "boom" and isinstance(s.errors[0][1], RuntimeError)
    assert s.pending() == []

def test_repeating_task_that_raises_is_rescheduled():
    s = Scheduler()
    def boom():
        raise ValueError("x")
    s.schedule("r", 1, boom, every=2)
    assert s.run_due(1) == ["r"]
    assert s.pending() == [(3, "r")]

def test_task_added_by_callback_waits_for_next_call():
    s = Scheduler()
    log, cb = collector()
    def spawn():
        s.schedule("child", 0, cb("child"))
    s.schedule("parent", 1, spawn)
    assert s.run_due(5) == ["parent"]
    assert s.run_due(5) == ["child"]

def test_cancel_by_earlier_callback():
    s = Scheduler()
    log, cb = collector()
    s.schedule("killer", 1, lambda: s.cancel("victim"))
    s.schedule("victim", 2, cb("victim"))
    assert s.run_due(5) == ["killer"]
    assert log == []

def test_pending_order_uses_first_scheduled_for_ties():
    s = Scheduler()
    s.schedule("second", 3, lambda: None)
    s.schedule("first", 3, lambda: None)
    assert s.pending() == [(3, "second"), (3, "first")]
""", r"""
class Scheduler:
    def __init__(self):
        self._tasks = {}      # name -> [run_at, seq, callback, every]
        self._seq = 0
        self.errors = []

    def schedule(self, name, run_at, callback, every=None):
        if name in self._tasks:
            raise ValueError("duplicate name")
        if every is not None and every <= 0:
            raise ValueError("every")
        self._tasks[name] = [run_at, self._seq, callback, every]
        self._seq += 1

    def cancel(self, name):
        return self._tasks.pop(name, None) is not None

    def pending(self):
        return [(t[0], n) for n, t in sorted(self._tasks.items(), key=lambda kv: (kv[1][0], kv[1][1]))]

    def run_due(self, now):
        due = sorted((n for n, t in self._tasks.items() if t[0] <= now), key=lambda n: (self._tasks[n][0], self._tasks[n][1]))
        ran = []
        for n in due:
            t = self._tasks.get(n)
            if t is None:
                continue
            try:
                t[2]()
            except Exception as e:
                self.errors.append((n, e))
            ran.append(n)
            if n in self._tasks:
                if t[3] is None:
                    del self._tasks[n]
                else:
                    while t[0] <= now:
                        t[0] += t[3]
        return ran
""")

task("cx_expression", "write", "complex", r"""
Write a function `evaluate(expr, variables=None)` that evaluates an arithmetic expression given as a string and
returns the result as a `float`.

Grammar and rules:
- Numbers are written with digits and an optional decimal point (`3`, `2.5`, `.5` is not allowed, `5.` is not allowed).
- Operators: `+`, `-`, `*`, `/`, `^` (power) and parentheses. Spaces are ignored.
- `^` binds tighter than everything else and is right-associative: `2^3^2` is 512. Unary minus binds tighter than `*`
  and `/` but looser than `^`: `-2^2` is -4, and `2^-1` is 0.5. A unary plus is not allowed.
- Names (letters and underscores) are looked up in the `variables` dict. An unknown name is an error.
- Functions: `min(a, b, ...)` and `max(a, b, ...)` with at least one argument, and `abs(x)` with exactly one. Arguments
  are expressions separated by commas.
- Every problem raises `ValueError`: an empty expression, unbalanced parentheses, two operators in a row (except a unary
  minus), a missing operand, trailing garbage, an unknown character, an unknown function or name, a wrong number of
  arguments, implicit multiplication such as `2(3)` or `2 3`, and division by zero.
""", r"""
import pytest
from solution import evaluate

def test_basic_arithmetic_and_precedence():
    assert evaluate("1 + 2 * 3") == 7
    assert evaluate("(1 + 2) * 3") == 9
    assert evaluate("10 - 4 - 3") == 3
    assert evaluate("8 / 4 / 2") == 1

def test_returns_float():
    assert type(evaluate("2 + 3")) is float

def test_power_rules():
    assert evaluate("2^3^2") == 512
    assert evaluate("-2^2") == -4
    assert evaluate("2^-1") == 0.5
    assert evaluate("2 * 3^2") == 18

def test_unary_minus():
    assert evaluate("-3 + 5") == 2
    assert evaluate("--3") == 3
    assert evaluate("4 * -2") == -8
    assert evaluate("-(2 + 3)") == -5

def test_decimals():
    assert evaluate("1.5 * 4") == 6.0
    assert abs(evaluate("0.1 + 0.2") - 0.3) < 1e-9

def test_variables():
    assert evaluate("x * y + 1", {"x": 3, "y": 4}) == 13
    assert evaluate("_a1b", {"_a1b": 2.5}) == 2.5

def test_functions():
    assert evaluate("max(1, 5, 3)") == 5
    assert evaluate("min(4)") == 4
    assert evaluate("abs(-7) + min(2, 1+0)") == 8
    assert evaluate("max(min(5, 9), 2) * 2") == 10

@pytest.mark.parametrize("bad", ["", "   ", "1 +", "* 2", "1 2", "2(3)", "(1", "1)", "1 ++ 2", "+3", "3 $ 4", "foo",
                                 "sin(1)", "abs(1, 2)", "abs()", "max()", "1 / 0", "5.", ".5", "2 ^", "min(1,)", "()"])
def test_invalid(bad):
    with pytest.raises(ValueError):
        evaluate(bad)

def test_division_by_zero_in_subexpression():
    with pytest.raises(ValueError):
        evaluate("1 / (2 - 2)")

def test_unknown_variable_with_other_variables():
    with pytest.raises(ValueError):
        evaluate("x + z", {"x": 1})
""", r"""
import re

TOKEN = re.compile(r"\s*(?:(\d+\.\d+|\d+)|([A-Za-z_][A-Za-z_0-9]*)|(.))")

def evaluate(expr, variables=None):
    variables = variables or {}
    toks = []
    pos = 0
    expr = expr.rstrip()
    while pos < len(expr):
        m = TOKEN.match(expr, pos)
        if not m:
            break
        if m[1]:
            if expr[m.end():m.end() + 1] == "." or False:
                raise ValueError("number")
            toks.append(("num", float(m[1])))
        elif m[2]:
            toks.append(("name", m[2]))
        else:
            if m[3] not in "+-*/^(),":
                raise ValueError("char")
            toks.append(("op", m[3]))
        pos = m.end()
    if not toks:
        raise ValueError("empty")
    i = [0]

    def peek():
        return toks[i[0]] if i[0] < len(toks) else (None, None)

    def take():
        t = peek()
        i[0] += 1
        return t

    def expect(op):
        if take() != ("op", op):
            raise ValueError("expected " + op)

    def expression():
        v = term()
        while peek() in (("op", "+"), ("op", "-")):
            op = take()[1]
            r = term()
            v = v + r if op == "+" else v - r
        return v

    def term():
        v = unary()
        while peek() in (("op", "*"), ("op", "/")):
            op = take()[1]
            r = unary()
            if op == "*":
                v *= r
            else:
                if r == 0:
                    raise ValueError("division by zero")
                v /= r
        return v

    def unary():
        if peek() == ("op", "-"):
            take()
            return -unary()
        return power()

    def power():
        base = atom()
        if peek() == ("op", "^"):
            take()
            return base ** unary()
        return base

    def atom():
        kind, val = take()
        if kind == "num":
            return val
        if kind == "name":
            if peek() == ("op", "("):
                take()
                args = []
                if peek() != ("op", ")"):
                    args.append(expression())
                    while peek() == ("op", ","):
                        take()
                        args.append(expression())
                expect(")")
                if val in ("min", "max") and args:
                    return float((min if val == "min" else max)(args))
                if val == "abs" and len(args) == 1:
                    return abs(args[0])
                raise ValueError("function")
            if val not in variables:
                raise ValueError("unknown name")
            return float(variables[val])
        if (kind, val) == ("op", "("):
            v = expression()
            expect(")")
            return v
        raise ValueError("operand")

    result = expression()
    if i[0] != len(toks):
        raise ValueError("trailing")
    return float(result)
""")

task("cx_ini_parser", "write", "complex", r"""
Write a function `parse_ini(text)` for a small INI dialect, specified here. It returns a dict that maps each section
name to a dict that maps keys to string values.

1. The text is processed line by line (lines are separated by `\n`; the first line is line 1). Leading and trailing
   whitespace of a line is ignored. Empty lines are skipped.
2. A line whose first character (after the whitespace) is `;` or `#` is a comment and is skipped.
3. `[name]` starts a section. The name is trimmed and must not be empty, and the line must end with `]` (after
   trimming). A section that is repeated continues the earlier one. A section with no keys still appears, as `{}`.
4. Every other line must be `key = value`. It is split at the first `=`. The key is trimmed and must not be empty.
   Keys before the first section go into the section named `""`, which appears in the result only if it has keys.
   If a key appears twice in a section, the later value wins.
5. The value (the text after the `=`, trimmed) is either quoted or unquoted.
   - Unquoted: an inline comment starts at the first `;` or `#` that has whitespace in front of it; the comment is cut
     off and the rest is trimmed. A `;` or `#` without whitespace in front of it belongs to the value
     (`color=#fff` has the value `#fff`). Backslashes are kept as they are. An empty value is allowed.
   - Quoted: the value starts with `"` and ends at the next `"` that is not escaped. Inside, `\"` is a double
     quote, `\\` is a backslash, `\n` is a newline and `\t` is a tab; any other backslash sequence is an error. After
     the closing quote only whitespace, or whitespace followed by a comment (`;` or `#`), may follow, otherwise it is an
     error. A quoted value keeps its inner spaces exactly.
6. Every error raises `ValueError`, and the message contains `line N` with the number of the offending line (for
   example `line 3`). Errors: a section header that is malformed or empty, a line without `=`, an empty key, an
   unterminated quoted value, a bad escape, text after a closing quote.
""", r"""
import pytest
from solution import parse_ini

def test_basic_sections():
    text = "[a]\nx = 1\ny=two words\n[b]\nz = 3\n"
    assert parse_ini(text) == {"a": {"x": "1", "y": "two words"}, "b": {"z": "3"}}

def test_comments_and_blank_lines():
    text = "; top\n\n# another\n[a]\n  ; indented\nx = 1\n"
    assert parse_ini(text) == {"a": {"x": "1"}}

def test_global_keys_go_to_empty_section_only_if_present():
    assert parse_ini("k = v\n[a]\nx=1") == {"": {"k": "v"}, "a": {"x": "1"}}
    assert "" not in parse_ini("[a]\nx=1")

def test_empty_section_kept():
    assert parse_ini("[empty]\n[a]\nx=1") == {"empty": {}, "a": {"x": "1"}}

def test_repeated_section_merges_and_later_key_wins():
    text = "[a]\nx=1\ny=2\n[b]\nq=1\n[a]\nx=9\n"
    assert parse_ini(text) == {"a": {"x": "9", "y": "2"}, "b": {"q": "1"}}

def test_inline_comments():
    text = "[a]\nx = 5 ; five\ny = 6 # six\ncolor=#fff\nurl = a;b\n"
    assert parse_ini(text) == {"a": {"x": "5", "y": "6", "color": "#fff", "url": "a;b"}}

def test_first_equals_splits():
    assert parse_ini("[a]\nformula = a=b+c\n") == {"a": {"formula": "a=b+c"}}

def test_empty_value():
    assert parse_ini("[a]\nx =\ny = ; just a comment\n") == {"a": {"x": "", "y": ""}}

def test_quoted_values_keep_spaces_and_comment_chars():
    text = '[a]\nx = "  padded ; not a comment  "\ny = "# also kept"\n'
    assert parse_ini(text) == {"a": {"x": "  padded ; not a comment  ", "y": "# also kept"}}

def test_quoted_escapes():
    text = r'[a]' + "\n" + r'x = "q\"uote \\ back\nline\ttab"' + "\n"
    assert parse_ini(text) == {"a": {"x": 'q"uote \\ back\nline\ttab'}}

def test_comment_after_quoted_value_allowed():
    assert parse_ini('[a]\nx = "v"   ; note\n') == {"a": {"x": "v"}}

def test_unquoted_backslash_kept():
    assert parse_ini("[a]\npath = C:\\temp\\new\n") == {"a": {"path": "C:\\temp\\new"}}

def test_section_name_trimmed():
    assert parse_ini("[  my section  ]\nx=1") == {"my section": {"x": "1"}}

def test_crlf_not_required_but_trailing_space_ok():
    assert parse_ini("[a]  \nx = 1   \n") == {"a": {"x": "1"}}

@pytest.mark.parametrize("text,line", [
    ("[a]\nx=1\nnovalue\n", 3),
    ("[a\nx=1\n", 1),
    ("[]\n", 1),
    ("[a]\n= 5\n", 2),
    ('[a]\nx = "open\n', 2),
    ('[a]\nx = "bad \\q escape"\n', 2),
    ('[a]\nx = "done" trailing\n', 2),
    ("\n\n[a]\nok=1\n[b] junk\n", 5),
])
def test_errors_name_the_line(text, line):
    with pytest.raises(ValueError) as e:
        parse_ini(text)
    assert f"line {line}" in str(e.value)
""", r"""
ESC = {'"': '"', "\\": "\\", "n": "\n", "t": "\t"}

def _quoted(rest, n):
    out, i = [], 1
    while i < len(rest):
        c = rest[i]
        if c == "\\":
            if i + 1 >= len(rest) or rest[i + 1] not in ESC:
                raise ValueError(f"line {n}: bad escape")
            out.append(ESC[rest[i + 1]])
            i += 2
        elif c == '"':
            tail = rest[i + 1:]
            if tail.strip() and not (tail[0] in " \t" and tail.strip()[0] in ";#"):
                raise ValueError(f"line {n}: text after closing quote")
            return "".join(out)
        else:
            out.append(c)
            i += 1
    raise ValueError(f"line {n}: unterminated quote")

def parse_ini(text):
    result, section = {}, ""
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.strip()
        if not line or line[0] in ";#":
            continue
        if line[0] == "[":
            if not line.endswith("]") or not line[1:-1].strip():
                raise ValueError(f"line {n}: bad section")
            section = line[1:-1].strip()
            result.setdefault(section, {})
            continue
        if "=" not in line:
            raise ValueError(f"line {n}: no '='")
        key, _, raw_rest = line.partition("=")
        key, rest = key.strip(), raw_rest.strip()
        if not key:
            raise ValueError(f"line {n}: empty key")
        if rest.startswith('"'):
            value = _quoted(rest, n)
        else:
            value = rest
            for i, c in enumerate(raw_rest):
                if c in ";#" and raw_rest[i - 1:i] in (" ", "\t"):
                    value = raw_rest[:i].strip()
                    break
        result.setdefault(section, {})[key] = value
    return result
""")

task("cx_shortest_path", "write", "complex", r"""
Write a function `shortest_path(graph, src, dst)` that finds the cheapest route in a directed weighted graph. `graph`
is a dict that maps a node to a dict of `{neighbour: weight}`. Weights are numbers greater than 0. A node may appear
only as a neighbour, with no entry of its own (it has no outgoing edges).

Return `(distance, path)` where `path` is the list of nodes from `src` to `dst`. If `src == dst` the result is
`(0, [src])`. If `dst` cannot be reached, return `None`. If several cheapest paths have the same distance, return the
one that comes first when the paths are compared as lists of node names (lexicographically). Raise `ValueError` if
`src` or `dst` appears nowhere in the graph (neither as a key nor as a neighbour), or if any weight is zero or
negative anywhere in the graph (even on an edge that is not used). The graph must not be modified.
""", r"""
import pytest
from solution import shortest_path

G = {"a": {"b": 7, "c": 9, "f": 14}, "b": {"a": 7, "c": 10, "d": 15}, "c": {"a": 9, "b": 10, "d": 11, "f": 2},
     "d": {"b": 15, "c": 11, "e": 6}, "e": {"d": 6, "f": 9}, "f": {"a": 14, "c": 2, "e": 9}}

def test_classic():
    assert shortest_path(G, "a", "e") == (20, ["a", "c", "f", "e"])

def test_same_node():
    assert shortest_path(G, "c", "c") == (0, ["c"])

def test_unreachable():
    g = {"a": {"b": 1}, "c": {"d": 1}}
    assert shortest_path(g, "a", "d") is None

def test_directed():
    g = {"a": {"b": 1}}
    assert shortest_path(g, "a", "b") == (1, ["a", "b"])
    assert shortest_path(g, "b", "a") is None

def test_node_only_as_neighbour():
    g = {"a": {"z": 4}}
    assert shortest_path(g, "a", "z") == (4, ["a", "z"])
    assert shortest_path(g, "z", "z") == (0, ["z"])

def test_tie_prefers_lexicographically_smaller_path():
    g = {"s": {"b": 1, "a": 1}, "a": {"t": 1}, "b": {"t": 1}}
    assert shortest_path(g, "s", "t") == (2, ["s", "a", "t"])

def test_tie_decided_late_in_the_path():
    g = {"s": {"m": 1}, "m": {"y": 1, "x": 1}, "x": {"t": 1}, "y": {"t": 1}}
    assert shortest_path(g, "s", "t") == (3, ["s", "m", "x", "t"])

def test_tie_between_different_lengths_in_hops():
    g = {"s": {"t": 4, "a": 1}, "a": {"b": 1}, "b": {"t": 2}}
    assert shortest_path(g, "s", "t") == (4, ["s", "a", "b", "t"])

def test_prefers_cheaper_over_fewer_hops():
    g = {"s": {"t": 10, "a": 1}, "a": {"t": 1}}
    assert shortest_path(g, "s", "t") == (2, ["s", "a", "t"])

def test_float_weights():
    g = {"a": {"b": 0.5, "c": 0.25}, "c": {"b": 0.125}}
    d, path = shortest_path(g, "a", "b")
    assert abs(d - 0.375) < 1e-12 and path == ["a", "c", "b"]

def test_cycles_do_not_hang():
    g = {"a": {"b": 1}, "b": {"a": 1, "c": 1}}
    assert shortest_path(g, "a", "c") == (2, ["a", "b", "c"])

def test_unknown_nodes():
    with pytest.raises(ValueError):
        shortest_path(G, "a", "nope")
    with pytest.raises(ValueError):
        shortest_path(G, "nope", "a")

def test_bad_weights_even_when_unused():
    with pytest.raises(ValueError):
        shortest_path({"a": {"b": 1}, "x": {"y": 0}}, "a", "b")
    with pytest.raises(ValueError):
        shortest_path({"a": {"b": -1}}, "a", "b")

def test_graph_not_modified():
    import copy
    g = copy.deepcopy(G)
    shortest_path(g, "a", "e")
    assert g == G
""", r"""
import heapq

def shortest_path(graph, src, dst):
    nodes = set(graph)
    for u, nb in graph.items():
        for v, w in nb.items():
            if w <= 0:
                raise ValueError("weight")
            nodes.add(v)
    if src not in nodes or dst not in nodes:
        raise ValueError("unknown node")
    heap = [(0, [src])]
    done = set()
    while heap:
        d, path = heapq.heappop(heap)
        u = path[-1]
        if u in done:
            continue
        done.add(u)
        if u == dst:
            return d, path
        for v, w in graph.get(u, {}).items():
            if v not in done:
                heapq.heappush(heap, (d + w, path + [v]))
    return None
""")

task("cx_schedule_algos", "write", "complex", r"""
Write two functions in one module.

1. `max_profit(jobs)`: `jobs` is a list of `(start, end, profit)` tuples with `start < end` and `profit >= 0`. Choose
   a set of jobs that do not overlap in time and have the largest total profit; return that total. Two jobs do not
   overlap if one ends at the same time as the other starts. An empty list gives 0. The input is not modified.
2. `min_rooms(meetings)`: `meetings` is a list of `(start, end)` tuples with `start < end`. Return the smallest number
   of rooms so that no two meetings in the same room overlap (a meeting ending at 10 and one starting at 10 can share a
   room). An empty list gives 0.
""", r"""
from solution import max_profit, min_rooms

def test_profit_basic():
    assert max_profit([(1, 3, 5), (2, 5, 6), (4, 6, 5), (6, 7, 4), (5, 8, 11), (7, 9, 2)]) == 17

def test_profit_touching_jobs_are_compatible():
    assert max_profit([(0, 5, 3), (5, 10, 4)]) == 7

def test_profit_prefers_one_big_job():
    assert max_profit([(0, 10, 100), (0, 5, 30), (5, 10, 30)]) == 100

def test_profit_empty_single_zero():
    assert max_profit([]) == 0
    assert max_profit([(1, 2, 9)]) == 9
    assert max_profit([(1, 2, 0), (2, 3, 0)]) == 0

def test_profit_unsorted_input_and_not_modified():
    jobs = [(6, 7, 4), (1, 3, 5), (5, 8, 11)]
    copy = list(jobs)
    assert max_profit(jobs) == 16
    assert jobs == copy

def test_profit_equal_ends_and_nested():
    assert max_profit([(1, 4, 5), (2, 4, 7), (4, 6, 2), (3, 5, 1)]) == 9

def test_rooms_basic():
    assert min_rooms([(0, 30), (5, 10), (15, 20)]) == 2

def test_rooms_touching_share_a_room():
    assert min_rooms([(0, 10), (10, 20), (20, 30)]) == 1

def test_rooms_all_overlap():
    assert min_rooms([(0, 10), (1, 9), (2, 8), (3, 7)]) == 4

def test_rooms_empty_and_unsorted():
    assert min_rooms([]) == 0
    assert min_rooms([(15, 20), (0, 30), (5, 10)]) == 2

def test_rooms_many_small_between_a_long_one():
    assert min_rooms([(0, 100), (1, 2), (2, 3), (3, 4)]) == 2
""", r"""
import bisect

def max_profit(jobs):
    js = sorted(jobs, key=lambda j: j[1])
    ends = [j[1] for j in js]
    best = [0] * (len(js) + 1)
    for i, (s, e, p) in enumerate(js, 1):
        k = bisect.bisect_right(ends, s, 0, i - 1)
        best[i] = max(best[i - 1], best[k] + p)
    return best[-1]

def min_rooms(meetings):
    events = []
    for s, e in meetings:
        events.append((s, 1))
        events.append((e, -1))
    events.sort()
    cur = top = 0
    for _, d in events:
        cur += d
        top = max(top, cur)
    return top
""")

task("cx_inventory_fix", "fix", "complex", r"""
Below are two modules of a small shop program, `inventory.py` and `orders.py`. For this exercise they must be merged:
return ONE module that defines `OutOfStock`, `Inventory` and `fulfil` (no imports between them).

The behaviour that is wrong, in words:
- `Inventory.remove(item, qty)` lets the stock become negative. It should raise `OutOfStock` when `qty` is more than the
  current stock, and then change nothing.
- `fulfil(inventory, order)` takes an order (a dict of item to quantity) and removes everything from the inventory. If
  one line cannot be served, the lines before it have already been removed. It must be all or nothing: on `OutOfStock`
  the inventory must be exactly as before the call.
- A quantity that is zero or negative, in `add`, `remove` or in an order, must raise `ValueError` (for an order, before
  anything is removed).
- `fulfil` returns the total number of items removed. An empty order returns 0.
- `Inventory.stock(item)` of an item never seen is 0. The inventory dict passed to the constructor must not be modified
  by later `add` or `remove` calls (copy it).

```python
# inventory.py
class OutOfStock(Exception):
    pass


class Inventory:
    def __init__(self, stock=None):
        self._stock = stock if stock is not None else {}

    def stock(self, item):
        return self._stock.get(item, 0)

    def add(self, item, qty):
        self._stock[item] = self.stock(item) + qty

    def remove(self, item, qty):
        self._stock[item] = self.stock(item) - qty
```

```python
# orders.py
from inventory import Inventory, OutOfStock


def fulfil(inventory, order):
    total = 0
    for item, qty in order.items():
        inventory.remove(item, qty)
        total += qty
    return total
```
""", r"""
import pytest
from solution import Inventory, OutOfStock, fulfil

def test_stock_of_unknown_item_is_zero():
    assert Inventory().stock("x") == 0

def test_add_and_remove():
    inv = Inventory({"a": 5})
    inv.add("a", 2)
    inv.add("b", 1)
    inv.remove("a", 7)
    assert inv.stock("a") == 0 and inv.stock("b") == 1

def test_remove_too_much_raises_and_changes_nothing():
    inv = Inventory({"a": 2})
    with pytest.raises(OutOfStock):
        inv.remove("a", 3)
    assert inv.stock("a") == 2

def test_remove_unknown_item_raises():
    with pytest.raises(OutOfStock):
        Inventory().remove("ghost", 1)

def test_constructor_dict_is_copied():
    base = {"a": 1}
    inv = Inventory(base)
    inv.add("a", 5)
    assert base == {"a": 1}

def test_bad_quantities_in_inventory():
    inv = Inventory({"a": 5})
    for bad in (0, -1):
        with pytest.raises(ValueError):
            inv.add("a", bad)
        with pytest.raises(ValueError):
            inv.remove("a", bad)
    assert inv.stock("a") == 5

def test_fulfil_success_returns_total():
    inv = Inventory({"apple": 5, "pear": 3})
    assert fulfil(inv, {"apple": 2, "pear": 3}) == 5
    assert inv.stock("apple") == 3 and inv.stock("pear") == 0

def test_fulfil_is_all_or_nothing():
    inv = Inventory({"apple": 5, "pear": 1})
    with pytest.raises(OutOfStock):
        fulfil(inv, {"apple": 2, "pear": 5})
    assert inv.stock("apple") == 5 and inv.stock("pear") == 1

def test_fulfil_failure_when_the_failing_line_is_first():
    inv = Inventory({"apple": 5})
    with pytest.raises(OutOfStock):
        fulfil(inv, {"pear": 1, "apple": 1})
    assert inv.stock("apple") == 5

def test_fulfil_bad_quantity_removes_nothing():
    inv = Inventory({"apple": 5, "pear": 5})
    with pytest.raises(ValueError):
        fulfil(inv, {"apple": 1, "pear": 0})
    assert inv.stock("apple") == 5

def test_fulfil_empty_order():
    inv = Inventory({"a": 1})
    assert fulfil(inv, {}) == 0
    assert inv.stock("a") == 1

def test_out_of_stock_is_an_exception_class():
    assert issubclass(OutOfStock, Exception)
""", r"""
class OutOfStock(Exception):
    pass


class Inventory:
    def __init__(self, stock=None):
        self._stock = dict(stock) if stock is not None else {}

    def stock(self, item):
        return self._stock.get(item, 0)

    def add(self, item, qty):
        if qty <= 0:
            raise ValueError("qty")
        self._stock[item] = self.stock(item) + qty

    def remove(self, item, qty):
        if qty <= 0:
            raise ValueError("qty")
        if qty > self.stock(item):
            raise OutOfStock(item)
        self._stock[item] = self.stock(item) - qty


def fulfil(inventory, order):
    for qty in order.values():
        if qty <= 0:
            raise ValueError("qty")
    for item, qty in order.items():
        if qty > inventory.stock(item):
            raise OutOfStock(item)
    total = 0
    for item, qty in order.items():
        inventory.remove(item, qty)
        total += qty
    return total
""", buggy=r"""
# inventory.py
class OutOfStock(Exception):
    pass


class Inventory:
    def __init__(self, stock=None):
        self._stock = stock if stock is not None else {}

    def stock(self, item):
        return self._stock.get(item, 0)

    def add(self, item, qty):
        self._stock[item] = self.stock(item) + qty

    def remove(self, item, qty):
        self._stock[item] = self.stock(item) - qty


# orders.py (merged: no import)
def fulfil(inventory, order):
    total = 0
    for item, qty in order.items():
        inventory.remove(item, qty)
        total += qty
    return total
""")

task("cx_template", "write", "complex", r"""
Write a function `render(template, context)` for a tiny template language, specified here. `context` is a dict.

1. Text outside tags is copied exactly as it is, whitespace included.
2. `{{ path }}` inserts a value. A path is names joined by dots, like `user.name` or `items.0`. The first name is looked
   up in `context`. Each further name is looked up in the current value: in a dict by key, in a list by index when the
   name is all digits. A name that cannot be found makes the whole value missing; a missing value renders as an empty
   string, and so does `None`. Any other value is converted with `str()`. Spaces inside the braces are ignored.
3. `{{ path | filter }}` applies one filter to the value. Filters: `upper`, `lower`, `title` (all work on `str(value)`;
   a missing value counts as an empty string) and `length` (the `len()` of the value, `0` when missing). An unknown filter
   raises `ValueError`.
4. `{% if path %}...{% endif %}` renders the body when the value is truthy (Python truthiness; missing is falsy). With
   `{% if not path %}` the test is reversed. An optional `{% else %}` starts the other branch.
5. `{% for name in path %}...{% endfor %}` renders the body once per item of the list found at `path` (nothing when it is
   missing). Inside the body, `name` is bound to the current item, and everything else in the context stays visible. After
   the loop, the context is as it was before.
6. Blocks can be nested in each other. A tag that is not closed, an `endif`, `else` or `endfor` without its opener, a
   mismatched closer, or a `{% %}` tag that is not one of the above, raises `ValueError`.
7. `{{` or `{%` that is never closed with `}}` or `%}` is plain text.
""", r"""
import pytest
from solution import render

def test_plain_text_exact():
    assert render("  hello\n world  ", {}) == "  hello\n world  "

def test_variable_and_spacing():
    assert render("Hi {{name}} and {{  name  }}!", {"name": "Ann"}) == "Hi Ann and Ann!"

def test_dotted_lookup_dict_and_list():
    ctx = {"user": {"name": "Bo", "tags": ["x", "y"]}}
    assert render("{{ user.name }} {{ user.tags.1 }}", ctx) == "Bo y"

def test_missing_and_none_render_empty():
    assert render("[{{ nope }}][{{ a.b.c }}][{{ n }}]", {"a": {}, "n": None}) == "[][][]"

def test_numbers_and_falsy_values_render():
    assert render("{{ n }}/{{ z }}/{{ f }}", {"n": 3, "z": 0, "f": False}) == "3/0/False"

def test_filters():
    assert render("{{ s | upper }} {{ s | lower }} {{ s | title }}", {"s": "hello World"}) == "HELLO WORLD hello world Hello World"
    assert render("{{ items | length }} {{ missing | length }} {{ s|length }}", {"items": [1, 2, 3], "s": "ab"}) == "3 0 2"
    assert render("[{{ nope | upper }}]", {}) == "[]"

def test_unknown_filter():
    with pytest.raises(ValueError):
        render("{{ x | reverse }}", {"x": "a"})

def test_if_else():
    t = "{% if flag %}yes{% else %}no{% endif %}"
    assert render(t, {"flag": 1}) == "yes"
    assert render(t, {"flag": 0}) == "no"
    assert render(t, {}) == "no"
    assert render(t, {"flag": [1]}) == "yes"

def test_if_not():
    t = "{% if not items %}empty{% endif %}"
    assert render(t, {"items": []}) == "empty"
    assert render(t, {"items": [1]}) == ""

def test_for_loop():
    assert render("{% for x in xs %}<{{ x }}>{% endfor %}", {"xs": [1, 2, 3]}) == "<1><2><3>"
    assert render("{% for x in xs %}<{{ x }}>{% endfor %}", {}) == ""

def test_for_sees_outer_context_and_restores_it():
    ctx = {"x": "outer", "sep": "-", "xs": ["a", "b"]}
    assert render("{% for x in xs %}{{ x }}{{ sep }}{% endfor %}{{ x }}", ctx) == "a-b-outer"
    assert ctx["x"] == "outer"

def test_for_over_dicts_with_paths():
    ctx = {"people": [{"n": "A", "ok": True}, {"n": "B", "ok": False}]}
    t = "{% for p in people %}{{ p.n }}{% if p.ok %}+{% else %}-{% endif %} {% endfor %}"
    assert render(t, ctx) == "A+ B- "

def test_nested_loops():
    t = "{% for r in rows %}[{% for c in r %}{{ c }}{% endfor %}]{% endfor %}"
    assert render(t, {"rows": [[1, 2], [3]]}) == "[12][3]"

def test_if_inside_for_inside_if():
    t = "{% if show %}{% for n in ns %}{% if n %}{{ n }}{% endif %}{% endfor %}{% endif %}"
    assert render(t, {"show": True, "ns": [0, 1, 2]}) == "12"
    assert render(t, {"show": False, "ns": [1]}) == ""

def test_unclosed_braces_are_text():
    assert render("a {{ b", {"b": 1}) == "a {{ b"
    assert render("a {% if", {}) == "a {% if"

@pytest.mark.parametrize("bad", ["{% if x %}a", "{% for i in xs %}a", "{% endif %}", "{% else %}", "{% endfor %}",
                                 "{% if x %}a{% endfor %}", "{% for i in xs %}a{% endif %}", "{% while x %}{% endwhile %}",
                                 "{% if x %}{% else %}{% else %}{% endif %}"])
def test_structure_errors(bad):
    with pytest.raises(ValueError):
        render(bad, {"x": 1, "xs": [1]})
""", r"""
import re

TAG = re.compile(r"(\{\{.*?\}\}|\{%.*?%\})", re.S)

def _lookup(path, ctx):
    cur = ctx
    for i, name in enumerate(path.split(".")):
        if i == 0 or isinstance(cur, dict):
            if isinstance(cur, dict) and name in cur:
                cur = cur[name]
                continue
            return None, False
        if isinstance(cur, list) and name.isdigit() and int(name) < len(cur):
            cur = cur[int(name)]
            continue
        return None, False
    return cur, True

def render(template, context):
    toks = [t for t in TAG.split(template) if t != ""]
    pos = [0]

    def block(ctx, stop):
        out = []
        while pos[0] < len(toks):
            t = toks[pos[0]]
            if t.startswith("{{"):
                pos[0] += 1
                body = t[2:-2].strip()
                filt = None
                if "|" in body:
                    body, _, filt = (x.strip() for x in body.partition("|"))
                v, ok = _lookup(body, ctx)
                if filt is not None:
                    if filt not in ("upper", "lower", "title", "length"):
                        raise ValueError("filter")
                    if filt == "length":
                        out.append(str(len(v) if ok and v is not None else 0))
                        continue
                    s = "" if not ok or v is None else str(v)
                    out.append(getattr(s, filt)())
                else:
                    out.append("" if not ok or v is None else str(v))
            elif t.startswith("{%"):
                words = t[2:-2].split()
                if not words:
                    raise ValueError("empty tag")
                if words[0] in ("endif", "else", "endfor"):
                    if words[0] in stop and len(words) == 1:
                        pos[0] += 1
                        return "".join(out), words[0]
                    raise ValueError("unexpected " + words[0])
                pos[0] += 1
                if words[0] == "if":
                    neg = len(words) == 3 and words[1] == "not"
                    if not (len(words) == 2 or neg):
                        raise ValueError("if")
                    v, ok = _lookup(words[-1], ctx)
                    truth = bool(v) if ok else False
                    if neg:
                        truth = not truth
                    yes, end = block(ctx, ("else", "endif"))
                    no = ""
                    if end == "else":
                        no, end = block(ctx, ("endif",))
                    if end != "endif":
                        raise ValueError("unclosed if")
                    out.append(yes if truth else no)
                elif words[0] == "for":
                    if len(words) != 4 or words[2] != "in":
                        raise ValueError("for")
                    v, ok = _lookup(words[3], ctx)
                    start = pos[0]
                    items = v if ok and isinstance(v, list) else []
                    if not items:
                        _, end = block(ctx, ("endfor",))
                        if end != "endfor":
                            raise ValueError("unclosed for")
                    for item in items:
                        pos[0] = start
                        body, end = block({**ctx, words[1]: item}, ("endfor",))
                        if end != "endfor":
                            raise ValueError("unclosed for")
                        out.append(body)
                else:
                    raise ValueError("unknown tag")
            else:
                pos[0] += 1
                out.append(t)
        return "".join(out), None

    result, end = block(dict(context), ())
    if end is not None:
        raise ValueError("stray tag")
    return result
""")


# tests with parametrize or loops count by what pytest collects (checked against the reference solutions in the unit tests)
for _id, _n in {"cx_expression": 31, "cx_ini_parser": 22, "cx_template": 24, "parse_duration": 8}.items():
    by_id_ = next(t for t in TASKS if t["id"] == _id)
    by_id_["n_tests"] = _n


def by_id(task_id: str) -> dict:
    return next(t for t in TASKS if t["id"] == task_id)
