"""check_claims reads dates, names and number formats as the same fact, and still catches every invented one."""
import json

import pytest

from minions import tools
from minions.errors import Invented, SchemaError


def ok(fake, cfg, text, source, claim_text, quote, supported=True):
    fake.replies.append(json.dumps({"claims": [{"claim": claim_text, "supported": supported, "quote": quote}]}))
    return tools.check_claims(cfg, text, source)["claims"][0]


def planted(fake, cfg, text, source, claim_text, quote, exc=Invented):
    fake.replies += [json.dumps({"claims": [{"claim": claim_text, "supported": True, "quote": quote}]})] * 2
    with pytest.raises(exc):
        tools.check_claims(cfg, text, source)


AUDIT = "The Brightwater audit closed on 2026-10-30. Anne-Marie Østergaard led it."


@pytest.mark.parametrize("text,claim_text", [
    ("The audit closed on 2026-10-30.", "The audit closed on 30 October 2026."),
    ("The audit closed on 30 Oct 2026.", "The audit closed on 30 Oct 2026."),
    ("The audit closed on 30 Oct 2026.", "The audit closed on 2026-10-30."),
    ("The audit closed on October 30, 2026.", "The audit closed on 30th October 2026."),
])
def test_dates_in_any_form_are_one_date(fake, cfg, text, claim_text):
    assert ok(fake, cfg, text, AUDIT, claim_text, "closed on 2026-10-30")["supported"] is True


def test_month_and_year_matches_a_source_date_in_that_month(fake, cfg):
    src = "Review date: 2026-10-14."
    assert ok(fake, cfg, "Review was in October 2026.", src, "Review was in October 2026.", "Review date")["supported"]
    assert ok(fake, cfg, "Review was in Oct 2026.", "The review took place in October 2026.",
              "Review was in Oct 2026.", "in October 2026")["supported"]


def test_a_wrong_date_is_still_invented(fake, cfg):
    planted(fake, cfg, "The audit closed on 2026-10-31.", AUDIT, "The audit closed on 31 October 2026.",
            "closed on 2026-10-30")
    planted(fake, cfg, "The audit closed on 30 November 2026.", AUDIT, "The audit closed on 30 November 2026.",
            "closed on 2026-10-30")
    planted(fake, cfg, "The review was in November 2026.", "Review date: 2026-10-14.",
            "The review was in November 2026.", "Review date")


NAMES = "Contact Zoë O'Brien-Lindqvist or Jean-Luc Dubois-Ström."


@pytest.mark.parametrize("name", ["Zoë O'Brien-Lindqvist", "Zoe O'Brien-Lindqvist", "Zoë O’Brien-Lindqvist",
                                  "Zoe OBrien-Lindqvist"])
def test_names_with_accents_apostrophes_and_hyphens(fake, cfg, name):
    c = ok(fake, cfg, f"{name} handled it.", NAMES, f"{name} handled it.", "Contact Zoë O'Brien-Lindqvist")
    assert c["supported"] is True


def test_an_invented_name_is_still_caught(fake, cfg):
    planted(fake, cfg, "Orla Dubois-Vennesund handled it.", NAMES, "Orla Dubois-Vennesund handled it.",
            "Contact Zoë O'Brien-Lindqvist")


COUNTS = "Totals: 1,712 files and a budget of 12 400 EUR."


@pytest.mark.parametrize("text,claim_text", [
    ("There were 1,712 files.", "There were 1712 files."),
    ("There were 1712 files.", "There were 1,712 files."),
    ("The budget was 12400 EUR.", "The budget was 12 400 EUR."),
    ("The budget was 12,400 EUR.", "The budget was 12400 EUR."),
])
def test_number_formats_are_one_number(fake, cfg, text, claim_text):
    assert ok(fake, cfg, text, COUNTS, claim_text, "1,712 files and a budget of 12 400 EUR")["supported"]


def test_a_number_not_in_the_source_is_still_invented(fake, cfg):
    planted(fake, cfg, "There were 1,721 files.", COUNTS, "There were 1,721 files.", "1,712 files")
    planted(fake, cfg, "The budget was 12 500 EUR.", COUNTS, "The budget was 12 500 EUR.", "budget of 12 400 EUR")


def test_a_different_number_in_the_claims_fails_the_call(fake, cfg):
    fake.replies += [json.dumps({"claims": [{"claim": "There were 1721 files.", "supported": False, "quote": ""}]})] * 2
    with pytest.raises(SchemaError):
        tools.check_claims(cfg, "There were 1,712 files.", COUNTS)


def test_a_quote_not_in_the_source_is_still_downgraded(fake, cfg):
    c = ok(fake, cfg, "The audit closed on 2026-10-30.", AUDIT, "The audit closed on 2026-10-30.",
           "closed on 2026-10-31")
    assert (c["supported"], c["flag"]) == (False, "quote_not_found")
    c = ok(fake, cfg, "There were 1,712 files.", COUNTS, "There were 1,712 files.", "1,721 files")
    assert c["flag"] == "quote_not_found"


def test_quote_reads_space_grouped_numbers(fake, cfg):
    c = ok(fake, cfg, "The budget was 12,400 EUR.", COUNTS, "The budget was 12,400 EUR.", "budget of 12,400 EUR")
    assert c["supported"]


def test_invalid_json_is_retried_once(fake, cfg):
    fake.replies.append('{"claims": [{"claim": "Entry was free."')   # cut off
    good = {"claims": [{"claim": "Entry was free.", "supported": True, "quote": "Entry was free"}]}
    fake.replies.append(json.dumps(good))
    out = tools.check_claims(cfg, "Entry was free.", "Entry was free. Hours: 9 to 5.")
    assert out["claims"][0]["supported"] is True
    assert "rejected" in fake.requests[1][1]["messages"][1]["content"]


def test_invalid_json_twice_still_fails(fake, cfg):
    fake.replies += ["not json", "still not json"]
    with pytest.raises(SchemaError):
        tools.check_claims(cfg, "Entry was free.", "Entry was free.")
