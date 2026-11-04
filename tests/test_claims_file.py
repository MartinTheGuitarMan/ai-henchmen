"""check_claims_file: a long source read from one named file, checked in chunks. Invented data only."""
import json

import pytest

from minions import claims, tools
from minions.config import Roster
from minions.errors import BadInput, PrivacyRefused, SchemaError

FACT_EARLY = "The Kelder Crane lifts up to 85 tonnes."
FACT_LATE = "The breakwater extension cost 4,350,000 crowns."


def long_file(tmp_path, fillers=700):
    fill = "\n".join(f"Entry {i}: the quay log noted {10000 + i} units." for i in range(fillers))
    p = tmp_path / "digest.txt"
    p.write_text(f"{FACT_EARLY}\n{fill}\n{FACT_LATE}\n", encoding="utf-8")
    return p


def answer(fake, *claims_):
    fake.replies.append(json.dumps({"claims": [{"claim": c, "supported": s, "quote": q} for c, s, q in claims_]}))


def by_chunk(fake, table):
    """Answer each request by which fact its SOURCE chunk holds: table = {marker: reply object}, else unsupported."""
    def dyn(body):
        content = body["messages"][1]["content"]
        for marker, obj in table.items():
            if marker in content.split("=====SOURCE=====")[1]:
                return json.dumps(obj)
        return json.dumps({"claims": [{"claim": CLAIM_LATE, "supported": False, "quote": ""}]})
    fake.dynamic = dyn


CLAIM_LATE = "The breakwater extension cost 4,350,000 crowns."


def test_chunks_cover_the_whole_source_with_overlap(tmp_path):
    src = long_file(tmp_path).read_text()
    parts = claims.chunks(src)
    assert len(src) > 12000 and 2 < len(parts) <= claims.MAX_CHUNKS
    assert all(len(p) <= claims.CHUNK for p in parts)
    assert FACT_EARLY in parts[0] and FACT_LATE in parts[-1]
    assert all(src.count(p) >= 1 for p in parts)                       # chunks are verbatim pieces
    assert set(src.splitlines()) <= {l for p in parts for l in p.splitlines()}   # no line is lost
    assert parts[0].splitlines()[-1] in parts[1]                       # the end of one chunk starts the next


def test_supported_in_a_late_chunk_is_supported(fake, cfg, tmp_path):
    by_chunk(fake, {"4,350,000": {"claims": [{"claim": CLAIM_LATE, "supported": True, "quote": "cost 4,350,000 crowns"}]}})
    out = tools.check_claims_file(cfg, CLAIM_LATE, str(long_file(tmp_path)))
    assert [c["supported"] for c in out["claims"]] == [True]
    assert out["chunks"] > 2 and out["chunks_failed"] == 0


def test_a_claim_no_chunk_supports_stays_unsupported(fake, cfg, tmp_path):
    other = "The Kelder Crane lifts up to 58 tonnes."
    fake.dynamic = lambda body: json.dumps({"claims": [{"claim": other, "supported": False, "quote": ""}]})
    out = tools.check_claims_file(cfg, other, str(long_file(tmp_path)))
    assert [c["supported"] for c in out["claims"]] == [False]


def test_short_file_is_one_plain_check(fake, cfg, tmp_path):
    p = tmp_path / "short.txt"
    p.write_text("The festival drew about 8,400 people. Entry was free.")
    answer(fake, ("About 8,400 people came.", True, "drew about 8,400 people"))
    out = tools.check_claims_file(cfg, "About 8,400 people came.", str(p))
    assert out["chunks"] == 1 and out["claims"][0]["supported"] and len(fake.requests) == 1


# ---- planted bad output: the code check still runs on every chunk
def test_planted_quote_not_in_any_chunk_is_downgraded(fake, cfg, tmp_path):
    by_chunk(fake, {"4,350,000": {"claims": [{"claim": CLAIM_LATE, "supported": True, "quote": "cost four million crowns"}]}})
    c = tools.check_claims_file(cfg, CLAIM_LATE, str(long_file(tmp_path)))["claims"][0]
    assert c["supported"] is False and c["flag"] == "quote_not_found"


def test_quote_from_another_chunk_does_not_support_this_chunks_claim(fake, cfg, tmp_path):
    # every chunk answers "supported" with the quote that only the LAST chunk holds: the other chunks must downgrade it
    reply = {"claims": [{"claim": CLAIM_LATE, "supported": True, "quote": "cost 4,350,000 crowns"}]}
    fake.dynamic = lambda body: json.dumps(reply)
    out = tools.check_claims_file(cfg, CLAIM_LATE, str(long_file(tmp_path)))
    assert out["claims"][0]["supported"] is True    # supported once, by the chunk that holds the quote
    first = long_file(tmp_path).read_text()[:claims.CHUNK]
    assert not claims.quote_found("cost 4,350,000 crowns", first)


def test_planted_number_not_in_the_source_fails_every_chunk(fake, cfg, tmp_path):
    reply = {"claims": [{"claim": "The breakwater extension cost 5,350,000 crowns.", "supported": True,
                         "quote": "cost 4,350,000 crowns"}]}
    fake.dynamic = lambda body: json.dumps(reply)
    out = tools.check_claims_file(cfg, "The breakwater extension cost 5,350,000 crowns.", str(long_file(tmp_path)))
    assert not any(c["supported"] for c in out["claims"])   # the chunk holding the quote raised MINION_INVENTED and was skipped
    assert out["chunks_failed"] >= 1


def test_planted_invented_name_is_never_supported(fake, cfg, tmp_path):
    text = "Harbourmaster Elias Brandvold opened the extension."
    reply = {"claims": [{"claim": text, "supported": True, "quote": "The breakwater extension cost"}]}
    fake.dynamic = lambda body: json.dumps(reply)
    out = tools.check_claims_file(cfg, text, str(long_file(tmp_path)))
    assert not any(c["supported"] for c in out["claims"]) and out["chunks_failed"] >= 1


def test_a_failing_chunk_is_counted_and_the_others_stand(fake, cfg, tmp_path):
    good = {"claims": [{"claim": CLAIM_LATE, "supported": True, "quote": "cost 4,350,000 crowns"}]}

    def dyn(body):
        src = body["messages"][1]["content"].split("=====SOURCE=====")[1]
        if "4,350,000" in src:
            return json.dumps(good)
        return "not json"
    fake.dynamic = dyn
    out = tools.check_claims_file(cfg, CLAIM_LATE, str(long_file(tmp_path)))
    assert out["claims"][0]["supported"] and out["chunks_failed"] == out["chunks"] - 1


def test_every_chunk_failing_raises(fake, cfg, tmp_path):
    fake.dynamic = lambda body: "not json"
    with pytest.raises(SchemaError):
        tools.check_claims_file(cfg, CLAIM_LATE, str(long_file(tmp_path)))


# ---- the file guard
def test_only_the_named_file_is_read(cfg, tmp_path):
    with pytest.raises(BadInput):
        tools.check_claims_file(cfg, CLAIM_LATE, str(tmp_path))                    # a folder
    with pytest.raises(BadInput):
        tools.check_claims_file(cfg, CLAIM_LATE, str(tmp_path / "*.txt"))          # no globbing
    with pytest.raises(BadInput):
        tools.check_claims_file(cfg, CLAIM_LATE, str(tmp_path / "missing.txt"))
    bin_ = tmp_path / "bin.txt"
    bin_.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(BadInput):
        tools.check_claims_file(cfg, CLAIM_LATE, str(bin_))


def test_a_file_over_the_chunk_limit_is_refused(cfg, tmp_path):
    p = tmp_path / "huge.txt"
    p.write_text("\n".join(f"line {i} with some padding text to fill the file" for i in range(3000)))
    assert len(claims.chunks(p.read_text())) > claims.MAX_CHUNKS
    with pytest.raises(BadInput, match="too long"):
        tools.check_claims_file(cfg, CLAIM_LATE, str(p))


def test_the_file_size_cap_applies(fake, tmp_path):
    cfg = Roster.single(__import__("minions.config", fromlist=["Config"]).Config(
        backend="lmstudio", base_url=fake.url, model="m", timeout=5, max_file_bytes=100))
    with pytest.raises(BadInput):
        tools.check_claims_file(cfg, CLAIM_LATE, str(long_file(tmp_path)))


def test_sensitive_stays_local(fake, monkeypatch, tmp_path):
    monkeypatch.setenv("UNUSED_TEST_KEY", "k")
    cloud = {"backend": "openai-compat", "base_url": fake.url, "model": "c", "timeout": 5, "cloud": True,
             "key_env": "UNUSED_TEST_KEY"}
    roster = Roster.from_dict({"models": {"c": cloud}})
    with pytest.raises(PrivacyRefused):
        tools.check_claims_file(roster, CLAIM_LATE, str(long_file(tmp_path)))     # default sensitive=True
    assert fake.requests == []


def test_merge_matches_reworded_claims():
    a = {"claims": [{"claim": "The breakwater extension cost 4,350,000 crowns.", "supported": False, "quote": ""}]}
    b = {"claims": [{"claim": "The breakwater extension cost 4350000 crowns", "supported": True, "quote": "q"}]}
    m = claims.merge([a, b])
    assert len(m) == 1 and m[0]["supported"] is True
