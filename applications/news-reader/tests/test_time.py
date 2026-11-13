"""Time handling (R2) against the shared cases, plus direct tests."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from newsreader.timeutil import (
    display_time, generated_at, generated_at_display, parse_time, published_utc,
)

CASES_FILE = Path(__file__).resolve().parent / "shared-cases.json"
TIME = json.loads(CASES_FILE.read_text(encoding="utf-8"))["time"]

REQUIRED_KINDS = [
    "rfc822-winter", "rfc822-summer", "gmt", "iso-z", "missing-zone", "invalid-text",
    "invalid-empty", "future-11", "future-9", "leap-day",
    "switch-spring-missing-hour", "switch-autumn-repeated-hour",
]
NOW = datetime(2026, 11, 13, 13, 5, 12, tzinfo=timezone.utc)


def utc_now(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def test_time_cases_have_id_input_expected():
    ids = [c["id"] for c in TIME]
    assert len(ids) == len(set(ids))
    for case in TIME:
        assert set(case) == {"id", "input", "expected"}
        assert set(case["input"]) == {"text", "now"}
        assert case["input"]["text"] is None or isinstance(case["input"]["text"], str)
        assert set(case["expected"]) == {"published", "publishedDisplay"}


def test_time_cases_cover_the_required_kinds():
    ids = " ".join(c["id"] for c in TIME)
    for kind in REQUIRED_KINDS:
        assert kind in ids, kind


@pytest.mark.parametrize("case", TIME, ids=[c["id"] for c in TIME])
def test_shared_time_case(case):
    published = published_utc(case["input"]["text"], utc_now(case["input"]["now"]))
    assert published == case["expected"]["published"]
    assert display_time(published) == case["expected"]["publishedDisplay"]


def test_parse_time_returns_aware_utc():
    moment = parse_time("Fri, 13 Nov 2026 14:05:00 +0100")
    assert moment == datetime(2026, 11, 13, 13, 5, tzinfo=timezone.utc)
    assert moment.utcoffset() == timedelta(0)


@pytest.mark.parametrize("value", [None, 5, b"2026-11-13T12:00:00Z", ""])
def test_parse_time_rejects_non_text_and_empty(value):
    assert parse_time(value) is None


def test_future_limit_is_exactly_ten_minutes():
    edge = "2026-11-13T13:15:12Z"
    assert published_utc(edge, NOW) == edge
    assert published_utc("2026-11-13T13:15:13Z", NOW) is None


def test_now_may_be_in_any_time_zone():
    from zoneinfo import ZoneInfo
    local_now = NOW.astimezone(ZoneInfo("Europe/Stockholm"))
    assert published_utc("2026-11-13T13:14:12Z", local_now) == "2026-11-13T13:14:12Z"
    assert published_utc("2026-11-13T13:16:12Z", local_now) is None


def test_display_of_null_is_tid_saknas():
    assert display_time(None) == "Tid saknas"


def test_display_summer_and_winter():
    assert display_time("2026-07-01T10:00:00Z") == "2026-07-01 12:00"
    assert display_time("2026-11-13T13:05:00Z") == "2026-11-13 14:05"


def test_display_rejects_text_that_is_not_utc():
    with pytest.raises(ValueError):
        display_time("2026-11-13 14:05")


def test_generated_at_and_display():
    assert generated_at(NOW) == "2026-11-13T13:05:12Z"
    assert generated_at_display(NOW) == "2026-11-13 14:05"
    summer = datetime(2026, 7, 1, 10, 0, 59, 999999, tzinfo=timezone.utc)
    assert generated_at(summer) == "2026-07-01T10:00:59Z"
    assert generated_at_display(summer) == "2026-07-01 12:00"


def test_year_edges_give_none_and_never_raise():
    for text in ["0001-01-01T00:30:00+01:00", "0001-01-01T00:30:00",
                 "9999-12-31T23:59:59-01:00", "0026-01-01T00:00:00Z",
                 "0999-12-31T23:59:59Z", "1969-12-31T23:59:59Z"]:
        assert published_utc(text, NOW) is None
        assert parse_time(text) is None


def test_output_years_are_zero_padded_by_hand():
    from newsreader.timeutil import format_utc
    early = datetime(26, 1, 1, tzinfo=timezone.utc)
    assert format_utc(early) == "0026-01-01T00:00:00Z"


def test_display_rejects_out_of_range_years_with_value_error():
    for text in ["9999-12-31T23:59:59Z"]:
        with pytest.raises(ValueError):
            display_time(text)


def test_fuzz_nothing_raises():
    import random
    rng = random.Random(20261113)
    alphabet = "0123456789:-+TZ ,.GMTUonvFri١"
    zones = ["", "Z", "GMT", "+0100", "-0100", "+99:99", "+01", " EST", " XYZ"]
    for _ in range(4000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 30)))
        assert published_utc(text, NOW) is None or isinstance(published_utc(text, NOW), str)
    for _ in range(6000):
        year = rng.choice([rng.randint(0, 20), rng.randint(0, 12000), 1969, 1970, 9998, 9999])
        fields = (year, rng.randint(0, 14), rng.randint(0, 33), rng.randint(0, 26),
                  rng.randint(0, 62), rng.randint(0, 62))
        zone = rng.choice(zones)
        iso = "%04d-%02d-%02dT%02d:%02d:%02d%s" % (fields + (zone.strip(),))
        rfc = "%02d %s %04d %02d:%02d:%02d%s" % (
            fields[2], rng.choice(["Jan", "Feb", "Dec", "Foo"]), year, fields[3],
            fields[4], fields[5], zone)
        for text in (iso, rfc):
            published = published_utc(text, NOW)
            if published is not None:
                assert display_time(published)
