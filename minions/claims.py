"""check_claims: split a text into claims and mark each one supported or not against a source.
A schema-valid reply is not an answer yet: every supported claim needs a quote found in the source (one whose quote is not found is
downgraded to unsupported with flag quote_not_found) and may only use numbers and capitalised names the source has, and no number or name of the text may drop out of the claims."""
from __future__ import annotations

import re
import unicodedata

from . import values
from .errors import Invented, SchemaError

MAX_CLAIMS = 40
SCHEMA = {"type": "object",
          "properties": {"claims": {"type": "array", "maxItems": MAX_CLAIMS, "items": {
              "type": "object",
              "properties": {"claim": {"type": "string"}, "supported": {"type": "boolean"}, "quote": {"type": "string"}},
              "required": ["claim", "supported", "quote"], "additionalProperties": False}}},
          "required": ["claims"], "additionalProperties": False}
TASK = ("The data holds a TEXT and a SOURCE. Split the TEXT into its separate factual claims, one fact each, and keep "
        "every one: do not leave any out. For each claim set supported to true only if the SOURCE states it; judge by "
        "the SOURCE alone, never by what you know. A claim with a number, name or date that the SOURCE does not have is "
        "not supported. For a supported claim put in quote the shortest passage copied exactly from the SOURCE that "
        "shows it; for a claim that is not supported leave quote empty.")


_MY = re.compile(rf"\b{values._MON}\s+(\d{{4}})\b", re.I)   # 'October 2026'


def _date_spans(text: str) -> list[tuple[int, int, set, tuple | None]]:
    """Dates written in text, in any form values.py reads, plus month-and-year ('October 2026'):
    (start, end, readings, (year, month) or None). Overlaps are skipped, full dates first."""
    spans: list = []

    def free(m) -> bool:
        return not any(m.start() < b and a < m.end() for a, b, _, _ in spans)

    for rx, _ in values.DATE_FORMS:
        for m in rx.finditer(text):
            if free(m) and (r := values._dates(m.group(0), whole=True)):
                spans.append((m.start(), m.end(), r, None))
    for m in _MY.finditer(text):
        if free(m):
            spans.append((m.start(), m.end(), set(), (int(m.group(2)), values.MONTHS[m.group(1).lower()])))
    return sorted(spans, key=lambda t: t[0])


class Facts:
    """What the source holds, normalised once: its numbers and words (values.Source), its dates and month-and-year
    mentions, its month numbers, and its words squashed together (so 'OBrien' finds 'O'Brien')."""

    def __init__(self, source: str):
        self.src = values.Source(source)
        spans = _date_spans(source)
        self.dates = set(self.src.dates).union(*[r for _, _, r, _ in spans])
        self.yms = {(d.year, d.month) for d in self.dates} | {ym for *_, ym in spans if ym}
        toks = self.src.folded.split()
        self.months = {m for _, m in self.yms} | {values.MONTHS[t] for t in toks if t in values.MONTHS}
        self.squashed = {"".join(toks[i:i + k]) for k in (1, 2, 3) for i in range(len(toks))}

    def has_span(self, readings: set, ym: tuple | None) -> bool:
        if ym:
            return ym in self.yms
        return bool(readings & self.dates)


def mask_dates(text: str, facts: "Facts | None") -> tuple[str, list]:
    """text with every date the source has (facts=None: every date at all) blanked out, so that '30 Oct 2026' and
    '2026-10-30' are not read as stray numbers and names, and the dates blanked: -> (masked, [(readings, ym)]).
    A date the source does not have stays in the text and is checked token by token, as before."""
    out, found, last = [], [], 0
    for a, b, r, ym in _date_spans(text):
        if facts is None or facts.has_span(r, ym):
            out += [text[last:a], " " * (b - a)]
            found.append((r, ym))
            last = b
    return "".join(out) + text[last:], found


def _month_ok(word: str, facts: Facts) -> bool:
    n = values.MONTHS.get(values._fold(word))
    return n is not None and n in facts.months


def terms(text: str, facts: "Facts | None") -> tuple[list[str], list[str]]:
    """(numbers, names) of text that the source does not have, plus all of them: -> (missing, all). Dates are
    left out of both when the source has them (in any form). facts=None describes the text itself: nothing missing."""
    masked, _ = mask_dates(text, facts)
    src = facts.src if facts else values.Source(text)
    missing, every = [], []
    for m in values._NUM.finditer(masked):
        every.append(m.group(0))
        if not values._number_ok(m.group(0), masked[m.end():], src):
            missing.append(m.group(0))
    for m in values._WORD_TOKEN.finditer(masked):
        w = values._ENDING.sub("", m.group(0))
        if w and values._is_name(w, masked[:m.start()]):
            every.append(w)
            if facts and not (values._word_ok(w, src) or _month_ok(w, facts)
                              or values._fold(w).replace(" ", "") in facts.squashed):
                missing.append(w)
    return missing, every


def left_out(text: str, claim_text: str) -> list[str]:
    """Numbers, names and dates of the text that no claim carries. Number formats (1,712 / 1712 / 1 712), date forms
    (2026-10-30 / 30 Oct 2026), month abbreviations, accents and apostrophes in names are all read as the same."""
    masked, wanted_dates = mask_dates(text, None)
    _, claim_dates = mask_dates(claim_text, None)
    cd = set().union(*[r for r, _ in claim_dates])
    cyms = {ym for _, ym in claim_dates if ym} | {(d.year, d.month) for d in cd}
    missing = [str(sorted(r)[0]) if r else f"{ym[1]}/{ym[0]}" for r, ym in wanted_dates
               if not ((ym in cyms) if ym else (r & cd))]
    _, every = terms(masked, None)
    cvals = {v for m in values._NUM.finditer(claim_text) for v in values._readings(m.group(0))[0]}
    folded = values._fold(claim_text)
    cmonths = {values.MONTHS[t] for t in folded.split() if t in values.MONTHS} | {m for _, m in cyms}
    for t in every:
        if t[0].isdigit():
            if not values._readings(t)[0] & cvals:
                missing.append(t)
        elif (n := values.MONTHS.get(values._fold(t))) is not None:
            if n not in cmonths:
                missing.append(t)
        elif values._fold(t) not in f" {folded} " and values._fold(t).replace(" ", "") not in folded.replace(" ", ""):
            missing.append(t)
    return missing


MIN_QUOTE = 3   # a quote shorter than this (non-space characters) proves nothing
_GROUP = re.compile(r"(?<=\d)[,'\u00a0\u2009\u202f](?=\d{3}(?!\d))")   # thousands separators: 1,712 -> 1712
_SPACED = re.compile(r"(?<![\d.,])\d{1,3}(?:[ \u00a0\u2009\u202f]\d{3}(?!\d))+")   # 12 400 -> 12400


def _ungroup(s: str) -> str:
    """Numbers without thousands separators (comma, apostrophe, space): 1,712 and 12 400 become 1712 and 12400."""
    return _SPACED.sub(lambda m: re.sub(r"\D", "", m.group(0)), _GROUP.sub("", s))
_EDGE = ".,;:!?\"'\u201c\u201d\u2018\u2019()[]"


def _norm(s: str) -> str:
    """The light normalisation of values.py (case, accents, punctuation, whitespace), with thousands separators
    removed from numbers first, so '1,712' and '1712' are one number. No fuzzy matching."""
    return f" {values._fold(_ungroup(s))} "


def quote_found(quote: str, source: str) -> bool:
    """The quote occurs in the source as whole words, after normalisation. Punctuation round the quote is ignored."""
    q = values._fold(_ungroup(quote.strip().strip(_EDGE)))
    return len(q.replace(" ", "")) >= MIN_QUOTE and f" {q} " in _norm(source)


# ---- hole 2: a returned claim must come from the input text
MIN_IN_TEXT = 0.65  # share of a claim's content words (and numbers) that must occur in the text, else it is dropped
# ---- hole 1: an unsupported claim with numbers is re-checked in code against single source lines
MIN_IN_LINE = 0.5   # share of the claim's non-number content words that must occur in that one line
_STOP = frozenset("""a an the and or but of in on at to for from by with as is are was were be been being it its this that these
those there here have has had do does did not no than then so such into over under about up down out also which who whom whose
what when where while their his her they them he she we you i our your can could will would may might should shall just very
more most some any all each both per via percent pct""".split())
_TOKEN = re.compile(r"\d+(?:\.\d+)?|[^\W\d_]+")
_NEGATION = frozenset("missing no not without none never lack lacks lacking lacked fail fails failed failing except".split())


def _negated(s: str) -> bool:
    """Any negation word (missing, no, not, without, lack, fail ...): a claim and its line must agree on it."""
    return any(w in _NEGATION for w in values._fold(s).split())


def _stem(w: str) -> str:
    for end in ("ing", "ed", "es", "s"):
        if w.endswith(end) and len(w) - len(end) >= 3:
            return w[:-len(end)]
    return w


def _tokens(s: str, side: bool = True) -> tuple[set[str], set[str]]:
    """(numbers and dates, stemmed content words) of s. Thousands separators are removed from numbers, so 1,712 is
    1712, and a date is one token in ISO form whatever its written form ('30 Oct 2026' is '2026-10-30'). side=True
    (the text or a source line) gives every reading of an ambiguous date; side=False (a claim) gives one."""
    nums, words = set(), set()
    masked, last = [], 0
    for a, b, r, ym in _date_spans(s):
        masked += [s[last:a], " "]
        last = b
        if ym:
            nums.add(f"{ym[0]}-{ym[1]:02d}")
        elif side:
            nums |= {d.isoformat() for d in r} | {f"{d.year}-{d.month:02d}" for d in r}
        else:
            d = min(r)
            nums |= {d.isoformat(), f"{d.year}-{d.month:02d}"}
    s = "".join(masked) + s[last:]
    for t in _TOKEN.findall(_fold_keep_dots(_ungroup(s))):
        if t[0].isdigit():
            nums.add(t)
        elif t not in _STOP and len(t) > 1:
            words.add(_stem(t))
    return nums, words


def _fold_keep_dots(s: str) -> str:
    """Case and accents folded; punctuation kept, so that 99.2 stays one number."""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).casefold()


def in_text(claim: str, text: str) -> bool:
    """The claim's content words and numbers mostly (MIN_IN_TEXT) occur in the text."""
    cn, cw = _tokens(claim, False)
    tn, tw = _tokens(text)
    wanted = cn | cw
    if not wanted:
        return True
    return len((cn & tn) | (cw & tw)) / len(wanted) >= MIN_IN_TEXT


def _lines(source: str) -> list[str]:
    out = []
    for raw in source.splitlines():
        out += [p.strip() for p in re.split(r"(?<=[.!?])\s+", raw) if p.strip()]
    return out


def line_for(claim: str, source: str) -> str | None:
    """A source line that holds every number of the claim (read as whole numbers, separators ignored) and most of its
    other content words, with the same negations. Only claims with a number qualify. -> the line, or None."""
    cn, cw = _tokens(claim, False)
    if not cn:
        return None
    cneg = _negated(claim)
    best = None
    for line in _lines(source):
        ln, lw = _tokens(line)
        lneg = _negated(line)
        if not cn <= ln or cneg != lneg:
            continue
        if cw and (len(cw & lw) < 1 or len(cw & lw) / len(cw) < MIN_IN_LINE):
            continue
        score = len(cw & lw)
        if best is None or score > best[0]:
            best = (score, line)
    return best[1] if best else None


def make_check(text: str, source: str, quote_found=quote_found):
    src = Facts(source)

    def check(obj: dict) -> None:
        kept = [c for c in obj["claims"] if not c["claim"].strip() or in_text(c["claim"], text)]
        extra = [c["claim"] for c in obj["claims"] if not any(c is k for k in kept)]
        if extra:
            obj["dropped_not_in_text"] = extra   # claims the model took from the source, not from the text
        obj["claims"] = claims = kept
        if not claims:
            raise SchemaError("no claims came back", str(obj)[:200])
        for c in claims:
            if not c["claim"].strip():
                raise SchemaError("a claim is empty", str(obj)[:200])
            if not c["supported"]:
                if c["quote"].strip():
                    c["quote"] = ""   # a quote on an unsupported claim proves nothing: dropped, not trusted
                line = line_for(c["claim"], source)
                if line and quote_found(line, source) and not terms(c["claim"], src)[0]:
                    c["supported"], c["quote"], c["flag"] = True, line, "rechecked_in_code"
                continue
            if not quote_found(c["quote"], source):
                # never trusted, but only this claim is lost: it is downgraded and flagged, the rest stands
                c["supported"], c["quote"], c["flag"] = False, "", "quote_not_found"
                continue
            missing, _ = terms(c["claim"], src)
            if missing:
                raise Invented(f"supported claim {c['claim'][:60]!r} names what the source does not: {missing}",
                               str(obj)[:200])
        dropped = left_out(text, " ".join(c["claim"] for c in claims))
        if dropped:
            raise SchemaError(f"claims leave out what the text says: {dropped[:5]}", str(obj)[:200])

    return check


# ---- check_claims_file: a source longer than check_claims takes is checked in overlapping chunks
CHUNK = 10000       # characters per chunk (check_claims takes 12,000)
OVERLAP = 600       # the end of one chunk starts the next, so a fact on a boundary is whole in one of them
MAX_CHUNKS = 10     # more than this is refused, never cut short
SAME_CLAIM = 0.75   # share of content words and numbers two claims must share to be the same claim


def chunks(source: str) -> list[str]:
    """The source in pieces of at most CHUNK characters, cut at line ends where possible, each piece starting with
    the last lines (up to OVERLAP characters) of the one before. Nothing is left out."""
    lines: list[str] = []
    for raw in source.splitlines(keepends=True):
        lines += [raw[i:i + CHUNK] for i in range(0, len(raw), CHUNK)] or [raw]
    out, cur = [], []
    for line in lines:
        if sum(map(len, cur)) + len(line) > CHUNK and cur:
            out.append("".join(cur))
            keep, size = [], 0
            for prev in reversed(cur):
                if size + len(prev) > OVERLAP:
                    break
                keep.insert(0, prev)
                size += len(prev)
            cur = keep
        cur.append(line)
    if cur:
        out.append("".join(cur))
    return out


def same_claim(a: str, b: str) -> bool:
    (an, aw), (bn, bw) = _tokens(a, False), _tokens(b, False)
    x, y = an | aw, bn | bw
    return bool(x and y) and len(x & y) / max(len(x), len(y)) >= SAME_CLAIM


def merge(results: list[dict]) -> list[dict]:
    """One claim list from the per-chunk results: a claim is supported when any chunk supported it (with a quote the
    code found in that chunk, hence in the source). Claims the chunks word differently are matched by shared content."""
    merged: list[dict] = []
    for res in results:
        for c in res["claims"]:
            hit = next((m for m in merged if same_claim(m["claim"], c["claim"])), None)
            if hit is None:
                merged.append(dict(c))
            elif c["supported"] and not hit["supported"]:
                hit.update(c)
            elif not hit["supported"] and c.get("flag") and not hit.get("flag"):
                hit["flag"] = c["flag"]
    return merged
