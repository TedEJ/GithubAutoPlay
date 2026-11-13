"""Item selection and the final item shape (R1.1, R1.4, R5.1 to R5.4, R9.1).

Hand-written data only; no network and no real feed content.
"""
import hashlib
import json
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from newsreader.keywords import load_keywords
from newsreader.model import NewsItem, RawEntry
from newsreader.select import (
    MAX_ITEMS, check_url, item_id, parse_url, select_items,
)

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s["id"]: s for s in json.loads((ROOT / "sources.json").read_text("utf-8"))["sources"]}
SVT = SOURCES["svt"]
NOW = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
HOSTS = ["svt.se"]
FIELDS = ["id", "sourceId", "sourceName", "title", "url", "published", "publishedDisplay"]


@pytest.fixture(scope="module")
def keywords():
    return load_keywords()


def entry(title="Riksdagen röstar", link="https://www.svt.se/a", time="2026-11-13T10:00:00Z",
          description=""):
    return RawEntry(title=title, link=link, time_text=time, description=description)


def select(entries, keywords=None, source=SVT, now=NOW):
    return select_items(entries, source, keywords, now)


def no_filter(**kw):
    """A source whose method is `feed` (no keyword filter), to test the other rules alone."""
    return {**SVT, "politics-sweden": {"method": "feed", "url": "https://www.svt.se/x.xml"}, **kw}


# ---- URL check (R9.1) --------------------------------------------------

GOOD_URLS = [
    "https://svt.se/a",
    "http://svt.se/a",
    "https://www.svt.se/nyheter/inrikes/a-b",
    "https://nyheter.svt.se/a",
    "https://a.b.svt.se/a",
    "HTTPS://WWW.SVT.SE/A",
    "https://SVT.se",
    "https://svt.se",
    "https://svt.se?x=1",
    "https://svt.se#top",
    "  https://svt.se/a \n",           # white space around the text is ignored
    "https://xn--bcher-kva.svt.se/a",  # punycode is ASCII, a subdomain of svt.se
]

BAD_URLS = [
    "",
    "   ",
    None,
    "svt.se/a",                        # no scheme
    "//svt.se/a",
    "/nyheter/a",
    "ftp://svt.se/a",
    "javascript:alert(1)",
    "data:text/html,x",
    "file:///etc/passwd",
    "https:svt.se/a",
    "https://",
    "https:///a",
    "https://evil.com/a",
    "https://evilsvt.se/a",            # ends with the text but is not a subdomain
    "https://svt.se.evil.com/a",
    "https://notsvt.se/a",
    "https://svt.se@evil.com/",        # user information
    "https://user:pw@svt.se/a",        # user information on a good host
    "https://evil.com@svt.se/a",
    "https://svt.se:443/a",            # any port is refused
    "http://svt.se:80/a",
    "https://svt.se:/a",
    "https://svt.se:evil.com/a",
    "https://svt.se./a",               # trailing dot
    "https://.svt.se/a",
    "https://www..svt.se/a",
    "https://svt.se\\@evil.com/",      # backslash
    "https://evil.com\\.svt.se/a",
    "https://svt.se/a\\b",
    "https://svt.se /a",               # white space inside
    "https://svt.se/a b",
    "https://svt.se/a\tb",
    "https://svt.se/a\nb",
    "https://svt.se/\x00",
    "https://svt.se/ö",                # non-ASCII anywhere
    "https://svt․se/a",           # one dot leader, not a dot
    "https://svt.se /a",     # NBSP inside is not trimmed here... (see below)
    "https://ѕvt.se/a",           # Cyrillic s: raw IDN lookalike
    "https://svt.se。/a",          # ideographic full stop
    "https://[::1]/a",
    "https://svt_.se/a",
    "https://svt.se%2f@evil.com/",
    "https://127.0.0.1/a",
    "https://sv%74.se/a",              # percent in the host
    "xhttps://svt.se/a",
    "https//svt.se/a",
]


@pytest.mark.parametrize("url", GOOD_URLS)
def test_good_urls_are_accepted(url):
    assert check_url(url, HOSTS) is not None


@pytest.mark.parametrize("url", BAD_URLS)
def test_bad_urls_are_refused(url):
    assert check_url(url, HOSTS) is None


def test_scheme_must_be_http_or_https_only():
    assert parse_url("http://svt.se/a")[0] == "http"
    assert parse_url("https://svt.se/a")[0] == "https"
    assert parse_url("HtTpS://svt.se/a")[0] == "https"
    assert parse_url("ws://svt.se/a") is None


def test_allowed_host_list_is_used_not_a_fixed_host():
    assert check_url("https://www.sverigesradio.se/a", ["sverigesradio.se"]) is not None
    assert check_url("https://svt.se/a", ["sverigesradio.se"]) is None
    assert check_url("https://svt.se/a", ["svt.se", "sverigesradio.se"]) is not None
    assert check_url("https://svt.se/a", []) is None


def test_host_is_checked_on_label_boundaries():
    assert check_url("https://xsvt.se/a", HOSTS) is None
    assert check_url("https://x.svt.se/a", HOSTS) is not None
    assert check_url("https://svt.se.x.svt.se/a", HOSTS) is not None
    # A subdomain of a subdomain host is allowed too.
    assert check_url("https://a.nyheter.svt.se/a", ["nyheter.svt.se"]) is not None
    assert check_url("https://svt.se/a", ["nyheter.svt.se"]) is None


# ---- normalisation (R5.3) ---------------------------------------------

@pytest.mark.parametrize("url, expected", [
    ("https://www.svt.se/a/b", "https://svt.se/a/b"),
    ("HTTPS://WWW.SVT.SE/a/B", "https://svt.se/a/B"),          # path keeps its case
    ("http://svt.se/a", "http://svt.se/a"),                    # scheme is kept (not unified)
    ("https://svt.se/a?x=1&y=2", "https://svt.se/a"),
    ("https://svt.se/a#frag", "https://svt.se/a"),
    ("https://svt.se/a?x=1#frag", "https://svt.se/a"),
    ("https://svt.se/a/", "https://svt.se/a"),
    ("https://svt.se/a//", "https://svt.se/a"),
    ("https://svt.se/", "https://svt.se"),
    ("https://svt.se", "https://svt.se"),
    ("https://svt.se/?x=1", "https://svt.se"),
    ("https://svt.se?x=1", "https://svt.se"),
    ("https://svt.se/a/?x=1", "https://svt.se/a"),
    ("https://www.www.svt.se/a", "https://www.svt.se/a"),      # only one www. is removed
    ("https://news.www.svt.se/a", "https://news.www.svt.se/a"),
    ("https://nyheter.svt.se/a", "https://nyheter.svt.se/a"),  # other subdomains stay
    ("https://svt.se/a%2Fb", "https://svt.se/a%2Fb"),          # no percent-decoding
    ("  https://svt.se/a/  ", "https://svt.se/a"),
])
def test_normalised_url(url, expected):
    assert check_url(url, HOSTS) == expected


# ---- id (R5.4) ---------------------------------------------------------

def test_id_is_first_16_hex_of_sha256_of_normalised_url():
    n = "https://svt.se/a"
    assert item_id(n) == hashlib.sha256(n.encode()).hexdigest()[:16]
    assert len(item_id(n)) == 16
    assert all(c in "0123456789abcdef" for c in item_id(n))


def test_id_is_the_same_for_urls_that_normalise_alike(keywords):
    a = select([entry(link="https://www.svt.se/a/?x=1")], keywords)[0]
    b = select([entry(link="http://svt.se/a")], keywords)[0]
    c = select([entry(link="https://SVT.se/a#z")], keywords)[0]
    assert a.id == c.id
    assert a.id != b.id  # scheme is part of the normalised URL
    assert a.id == item_id("https://svt.se/a")


# ---- the final item shape (R1.1) ---------------------------------------

def test_item_has_exactly_the_r11_fields(keywords):
    items = select([entry(description="Lång text som aldrig ska publiceras")], keywords)
    assert len(items) == 1
    item = items[0]
    assert [f.name for f in fields(NewsItem)] == FIELDS
    assert list(item.as_dict()) == FIELDS
    assert not hasattr(item, "description")
    assert item.as_dict() == {
        "id": item_id("https://svt.se/a"),
        "sourceId": "svt",
        "sourceName": "SVT",
        "title": "Riksdagen röstar",
        "url": "https://www.svt.se/a",
        "published": "2026-11-13T10:00:00Z",
        "publishedDisplay": "2026-11-13 11:00",
    }
    assert "aldrig" not in json.dumps(item.as_dict())


def test_item_can_not_get_extra_fields():
    with pytest.raises(TypeError):
        NewsItem(id="x", sourceId="s", sourceName="S", title="t", url="u",
                 published=None, publishedDisplay="Tid saknas", description="no")


def test_item_is_json_serialisable(keywords):
    item = select([entry()], keywords)[0]
    assert json.loads(json.dumps(item.as_dict(), ensure_ascii=False)) == item.as_dict()


def test_title_is_cleaned_and_url_keeps_original_form(keywords):
    e = entry(title="  <b>Riksdagen</b> &amp;\n  regeringen ", link="  https://WWW.svt.se/A/?x=1 ")
    item = select([e], keywords)[0]
    assert item.title == "Riksdagen & regeringen"
    assert item.url == "https://WWW.svt.se/A/?x=1"   # trimmed, otherwise as in the feed


def test_long_title_is_not_cut(keywords):
    title = "Riksdagen " + "x" * 300
    assert select([entry(title=title)], keywords)[0].title == title


def test_source_fields_come_from_the_source(keywords):
    src = {**SVT, "id": "other", "name": "Other"}
    item = select([entry()], keywords, source=src)[0]
    assert (item.sourceId, item.sourceName) == ("other", "Other")


def test_time_fields_come_from_timeutil(keywords):
    summer = select([entry(time="Wed, 01 Jul 2026 10:00:00 +0000")], keywords,
                    now=datetime(2026, 7, 2, tzinfo=timezone.utc))[0]
    assert (summer.published, summer.publishedDisplay) == ("2026-07-01T10:00:00Z", "2026-07-01 12:00")
    none = select([entry(time="")], keywords)[0]
    assert (none.published, none.publishedDisplay) == (None, "Tid saknas")
    bad = select([entry(time="yesterday")], keywords)[0]
    assert (bad.published, bad.publishedDisplay) == (None, "Tid saknas")
    future = select([entry(time="2026-11-13T12:11:00Z")], keywords)[0]  # > 10 minutes ahead
    assert future.published is None
    near = select([entry(time="2026-11-13T12:10:00Z")], keywords)[0]
    assert near.published == "2026-11-13T12:10:00Z"


# ---- dropping items (R1.4, R9.1) ---------------------------------------

def test_empty_title_is_dropped():
    src = no_filter()
    for title in ["", "   ", " \t\n", "<b></b>", "<i> </i>", "&nbsp;", "<!-- x -->"]:
        assert select([entry(title=title)], source=src) == [], repr(title)
    assert len(select([entry(title="<b>x</b>")], source=src)) == 1


def test_missing_or_invalid_url_is_dropped():
    src = no_filter()
    assert select([entry(link="")], source=src) == []
    for url in BAD_URLS:
        if url is None:
            continue
        assert select([entry(link=url)], source=src) == [], repr(url)
    assert len(select([entry(link="https://svt.se/a")], source=src)) == 1


def test_only_bad_items_are_dropped_and_order_follows_time():
    src = no_filter()
    got = select([
        entry(title="a", link="https://evil.com/a", time="2026-11-13T11:00:00Z"),
        entry(title="b", link="https://svt.se/b", time="2026-11-13T09:00:00Z"),
        entry(title="", link="https://svt.se/c", time="2026-11-13T11:00:00Z"),
        entry(title="d", link="javascript:x", time="2026-11-13T11:00:00Z"),
        entry(title="e", link="https://svt.se/e", time="2026-11-13T10:00:00Z"),
    ], source=src)
    assert [i.title for i in got] == ["e", "b"]


def test_empty_input_gives_empty_list(keywords):
    assert select([], keywords) == []


# ---- keyword filter (R4.4) ---------------------------------------------

def test_keyword_filter_uses_title_and_description(keywords):
    got = select([
        entry(title="Väder i helgen", link="https://svt.se/1"),
        entry(title="Regeringen presenterar", link="https://svt.se/2"),
        entry(title="Något annat", link="https://svt.se/3", description="<p>Om riksdagen</p>"),
        entry(title="Tyska regeringen sänker skatten", link="https://svt.se/4"),
    ], keywords)
    assert sorted(i.url for i in got) == ["https://svt.se/2", "https://svt.se/3"]


def test_source_without_keyword_filter_keeps_everything():
    got = select([entry(title="Väder i helgen")], source=no_filter())
    assert len(got) == 1


def test_which_sources_filter_comes_from_sources_json(keywords):
    # Both current sources say keywordFilter, so both filter.
    for src in SOURCES.values():
        assert src["politics-sweden"]["method"] == "keywordFilter"
        assert select([entry(title="Väder i helgen", link="https://sverigesradio.se/1")],
                      keywords, source=src) == []


def test_keywords_are_required_for_keyword_filter():
    with pytest.raises(ValueError):
        select([entry()], None)


def test_unsupported_method_is_an_error(keywords):
    src = {**SVT, "politics-sweden": {"method": "categoryFilter", "url": "https://svt.se/x"}}
    with pytest.raises(ValueError):
        select([entry()], keywords, source=src)


def test_description_is_never_part_of_the_item(keywords):
    got = select([entry(title="Regeringen", description="SECRETTEXT riksdagen")], keywords)
    assert "SECRETTEXT" not in repr(got)


def test_item_failing_url_check_does_not_hide_a_later_duplicate_candidate(keywords):
    got = select([
        entry(link="https://evil.com/a"),
        entry(link="https://svt.se/a"),
    ], keywords)
    assert [i.url for i in got] == ["https://svt.se/a"]


# ---- duplicates (R5.3) -------------------------------------------------

def test_duplicates_by_normalised_url_keep_the_first_in_feed_order(keywords):
    got = select([
        entry(title="Riksdagen först", link="https://www.svt.se/a/", time="2026-11-13T08:00:00Z"),
        entry(title="Riksdagen andra", link="http://svt.se/a", time="2026-11-13T11:00:00Z"),  # other scheme: different
        entry(title="Riksdagen tredje", link="https://SVT.se/a?x=1", time="2026-11-13T11:30:00Z"),
        entry(title="Riksdagen fjärde", link="https://svt.se/a#f", time="2026-11-13T11:45:00Z"),
        entry(title="Riksdagen femte", link="https://svt.se/b", time="2026-11-13T07:00:00Z"),
    ], keywords)
    titles = sorted(i.title for i in got)
    assert titles == ["Riksdagen andra", "Riksdagen femte", "Riksdagen först"]


def test_duplicate_is_checked_after_the_other_rules(keywords):
    # The first entry with this URL is dropped (no keyword), so the second is the first kept.
    got = select([
        entry(title="Väder", link="https://svt.se/a"),
        entry(title="Riksdagen", link="https://svt.se/a?x"),
    ], keywords)
    assert [i.title for i in got] == ["Riksdagen"]


def test_different_paths_are_not_duplicates():
    got = select([entry(link="https://svt.se/a"), entry(link="https://svt.se/A"),
                  entry(link="https://svt.se/a/b")], source=no_filter())
    assert len(got) == 3


def test_same_url_in_different_calls_is_not_removed(keywords):
    # De-duplication is per source (per call), never across sources.
    assert len(select([entry()], keywords)) == 1
    assert len(select([entry()], keywords, source={**SVT, "id": "x"})) == 1


# ---- age limit (R5.2) --------------------------------------------------

def test_age_limit_is_seven_days():
    src = no_filter()
    cutoff = NOW - timedelta(days=7)

    def at(moment):
        return select([entry(time=moment.strftime("%Y-%m-%dT%H:%M:%SZ"))], source=src)

    assert len(at(cutoff)) == 1                              # exactly 7 days: kept
    assert at(cutoff - timedelta(seconds=1)) == []           # older: dropped
    assert len(at(cutoff + timedelta(seconds=1))) == 1
    assert at(NOW - timedelta(days=30)) == []


def test_age_limit_with_microseconds_in_now():
    src = no_filter()
    now = NOW + timedelta(microseconds=500000)
    # Exactly 7 days minus 0.5 s before `now` is 1 s too old only if it is before the cutoff.
    assert select([entry(time="2026-11-06T12:00:00Z")], source=src, now=now) == []
    assert len(select([entry(time="2026-11-06T12:00:01Z")], source=src, now=now)) == 1


def test_age_limit_uses_utc_instants_not_text():
    src = no_filter()
    assert len(select([entry(time="Fri, 06 Nov 2026 13:00:00 +0100")], source=src)) == 1
    assert select([entry(time="Fri, 06 Nov 2026 12:59:59 +0100")], source=src) == []


def test_now_may_have_any_time_zone():
    src = no_filter()
    now = datetime(2026, 11, 13, 13, 0, 0, tzinfo=timezone(timedelta(hours=1)))
    assert len(select([entry(time="2026-11-06T12:00:00Z")], source=src, now=now)) == 1
    assert select([entry(time="2026-11-06T11:59:59Z")], source=src, now=now) == []


def test_item_without_time_is_not_dropped_by_age():
    assert len(select([entry(time="")], source=no_filter())) == 1


def test_future_time_item_is_kept_without_time():
    got = select([entry(time="2027-01-01T00:00:00Z")], source=no_filter())
    assert len(got) == 1 and got[0].published is None


# ---- sorting and the cap (R5.1) ----------------------------------------

def many(n, minutes_apart=1, start=NOW - timedelta(hours=1), prefix="n"):
    out = []
    for i in range(n):
        t = start - timedelta(minutes=i * minutes_apart)
        out.append(entry(title="%s%03d" % (prefix, i), link="https://svt.se/%s/%d" % (prefix, i),
                         time=t.strftime("%Y-%m-%dT%H:%M:%SZ")))
    return out


def test_cap_constant():
    assert MAX_ITEMS == 20


def test_sorted_newest_first():
    entries = many(5)
    entries.reverse()  # oldest first in the feed
    got = select(entries, source=no_filter())
    assert [i.title for i in got] == ["n000", "n001", "n002", "n003", "n004"]
    assert [i.published for i in got] == sorted((i.published for i in got), reverse=True)


def test_cap_keeps_the_20_newest():
    entries = many(35)
    entries.reverse()
    got = select(entries, source=no_filter())
    assert len(got) == 20
    assert [i.title for i in got] == ["n%03d" % i for i in range(20)]


def test_exactly_20_and_19_are_kept():
    assert len(select(many(20), source=no_filter())) == 20
    assert len(select(many(19), source=no_filter())) == 19
    assert len(select(many(21), source=no_filter())) == 20


def test_null_times_come_last_and_only_fill_up_to_20():
    dated = many(5, prefix="d")
    undated = [entry(title="u%02d" % i, link="https://svt.se/u/%d" % i, time="") for i in range(30)]
    got = select(undated + dated, source=no_filter())
    assert len(got) == 20
    assert [i.title for i in got[:5]] == ["d000", "d001", "d002", "d003", "d004"]
    assert all(i.published is None for i in got[5:])
    assert len([i for i in got if i.published is None]) == 15


def test_dated_items_beat_undated_even_when_old():
    old = entry(title="old", link="https://svt.se/old", time=(NOW - timedelta(days=6)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    none = entry(title="none", link="https://svt.se/none", time="")
    assert [i.title for i in select([none, old], source=no_filter())] == ["old", "none"]


def test_full_dated_list_leaves_no_room_for_undated():
    got = select(many(20) + [entry(title="u", link="https://svt.se/u", time="")], source=no_filter())
    assert len(got) == 20 and all(i.published is not None for i in got)


def test_cap_is_applied_after_age_and_duplicates():
    old = [entry(title="old%d" % i, link="https://svt.se/old/%d" % i,
                 time=(NOW - timedelta(days=9, minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ")) for i in range(10)]
    dup = [entry(title="dup", link="https://svt.se/dup", time="2026-11-13T11:59:00Z")] * 10
    got = select(old + dup + many(19), source=no_filter())
    assert len(got) == 20            # 19 + one "dup" (the old ones and 9 duplicates are gone)
    assert "dup" in [i.title for i in got]


def test_cap_is_applied_after_the_keyword_filter(keywords):
    other = [entry(title="Väder %d" % i, link="https://svt.se/w/%d" % i,
                   time=(NOW - timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ")) for i in range(30)]
    pol = [entry(title="Riksdagen %d" % i, link="https://svt.se/p/%d" % i,
                 time=(NOW - timedelta(hours=2, minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ")) for i in range(3)]
    got = select(other + pol, keywords)
    assert len(got) == 3


def test_equal_times_are_ordered_by_title_then_feed_order():
    t = "2026-11-13T10:00:00Z"
    got = select([
        entry(title="b", link="https://svt.se/1", time=t),
        entry(title="Z", link="https://svt.se/2", time=t),      # capitals sort before small letters
        entry(title="a", link="https://svt.se/3", time=t),
        entry(title="b", link="https://svt.se/4", time=t),      # same title: feed order
    ], source=no_filter())
    assert [(i.title, i.url[-1]) for i in got] == [("Z", "2"), ("a", "3"), ("b", "1"), ("b", "4")]


def test_equal_times_compare_titles_by_code_point():
    t = "2026-11-13T10:00:00Z"
    got = select([
        entry(title="\U0001F600", link="https://svt.se/1", time=t),   # U+1F600
        entry(title="Ａ", link="https://svt.se/2", time=t),       # U+FF21 (below U+1F600)
    ], source=no_filter())
    assert [i.url[-1] for i in got] == ["2", "1"]


def test_undated_items_are_ordered_by_title():
    got = select([entry(title="b", link="https://svt.se/1", time=""),
                  entry(title="a", link="https://svt.se/2", time="")], source=no_filter())
    assert [i.title for i in got] == ["a", "b"]


def test_same_minute_different_offsets_sort_by_instant():
    got = select([
        entry(title="x", link="https://svt.se/1", time="Fri, 13 Nov 2026 12:00:00 +0100"),  # 11:00Z
        entry(title="y", link="https://svt.se/2", time="Fri, 13 Nov 2026 11:30:00 +0000"),  # 11:30Z
    ], source=no_filter())
    assert [i.title for i in got] == ["y", "x"]


def test_input_is_not_changed():
    entries = many(3)
    before = list(entries)
    select(entries, source=no_filter())
    assert entries == before


# ---- with the fixture feed ---------------------------------------------

def test_fixture_feed_gives_valid_items():
    from newsreader.parse import parse_rss
    raw = parse_rss((ROOT / "tests" / "fixtures" / "rss_svt_shape.xml").read_bytes())
    src = no_filter(allowedHosts=["example.invalid"])
    got = select_items(raw, src, None, datetime(2026, 11, 14, tzinfo=timezone.utc))
    assert got  # the fixture is invented and uses example.invalid
    for item in got:
        assert list(item.as_dict()) == FIELDS
        assert check_url(item.url, src["allowedHosts"]) is not None
        assert item.title and item.title == item.title.strip()
    assert len({i.id for i in got}) == len(got)
    stamps = [i.published for i in got if i.published]
    assert stamps == sorted(stamps, reverse=True)
