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
    if kind == "fix":
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


def by_id(task_id: str) -> dict:
    return next(t for t in TASKS if t["id"] == task_id)
