"""Riksdagen as a build source (F6: R16.1 to R16.4, R16.6, R16.7, R9.1 `linkHosts`).

Uses hand-written, invented samples in the shape of the Riksdag document list and the
project's own `sources.json` with the Riksdagen entry switched on (the real entry is
`enabled: false`, R16.9, D41: switched off by the owner). Nothing touches the network.
"""
import json
from datetime import datetime, timezone

import pytest

from newsreader.build import build
from newsreader.fetch import FetchError
from newsreader.parse import MAX_RESPONSE_BYTES, FeedError, parse_rss
from newsreader.select import check_url
from newsreader.timeutil import display_time, parse_time, published_utc
from tests.fakes import APP, NOW, FakeFetch
from tests.test_build import ROBOTS_OK, run, source_entry

FEED_URL = ("https://data.riksdagen.se/dokumentlista/?doktyp=prop,bet&sort=datum&sortorder=desc"
            "&utformat=rss&a=s&sz=50")
ROBOTS = "https://data.riksdagen.se/robots.txt"
BASE = "https://www.riksdagen.se/sv/dokument-och-lagar/dokument/"
SAMPLE = (APP / "tests" / "fixtures" / "rss_riksdagen_shape.xml").read_bytes()
NOT_FOUND = FetchError("status", "HTTP status 404", 404)  # R6.6: no rules, allowed


def real_riksdagen(enabled=True):
    sources = json.loads((APP / "sources.json").read_text(encoding="utf-8"))["sources"]
    entry = next(s for s in sources if s["id"] == "riksdagen")
    return {**entry, "enabled": enabled}


def setup(project, enabled=True):
    project.write_sources(real_riksdagen(enabled))


def items_of(document):
    return {i["url"][len(BASE):]: i for i in document["items"]}


def feed(*items, channel=""):
    """items: (title, link, pubDate) -> RSS 2.0 bytes in the Riksdag shape."""
    body = "".join("<item><title>%s</title><link>%s</link><pubDate>%s</pubDate>"
                   "<description>bet. 2026/27:X</description></item>" % i for i in items)
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>x</title>%s%s'
            "</channel></rss>" % (channel, body)).encode("utf-8")


def good_fetch(body=SAMPLE):
    return FakeFetch({ROBOTS: NOT_FOUND, FEED_URL: body})


# ---- the sample ---------------------------------------------------------

def test_the_sample_gives_six_items_with_title_link_and_time_only(project):
    setup(project)
    fetch = good_fetch()
    document = run(project, fetch)
    assert source_entry(document, "riksdagen")["status"] == "ok"
    assert len(document["items"]) == 6
    for item in document["items"]:
        assert set(item) == {"id", "sourceId", "sourceName", "title", "url", "published",
                             "publishedDisplay", "topics"}
        assert item["sourceId"] == "riksdagen" and item["sourceName"] == "Riksdagen"
        assert item["url"].startswith(BASE)


def test_one_robots_read_and_one_feed_request_for_the_three_feed_entries(project):
    # R16.3, R16.4: the feed host is data.riksdagen.se; the build never fetches www.riksdagen.se.
    setup(project)
    fetch = good_fetch()
    run(project, fetch)
    assert fetch.calls == [ROBOTS, FEED_URL]
    assert all("://www.riksdagen.se" not in call for call in fetch.calls)


def test_robots_404_means_allowed_and_robots_rules_are_obeyed(project):
    setup(project)
    blocked = FakeFetch({ROBOTS: b"User-agent: *\nDisallow: /dokumentlista/\n", FEED_URL: SAMPLE})
    document = run(project, blocked)
    assert source_entry(document, "riksdagen")["status"] == "blocked-by-robots"
    assert document["items"] == []
    assert blocked.calls == [ROBOTS]


def test_topics_all_news_and_politics_for_every_item_and_ai_by_the_title_only(project):
    setup(project)
    items = items_of(run(project, good_fetch()))
    assert len(items) == 6
    ai = [i for i in items.values() if "ai" in i["topics"]]
    assert [i["title"] for i in ai] == ["Betänkande om AI i offentlig sektor"]
    # An AI word only in the description gives no AI topic (matchOn title, R16.2).
    water = items["betankande/vattenforsorjning_hc01mju2"]
    assert water["topics"] == ["all-news", "politics"]
    for item in items.values():
        assert item["topics"][:2] == ["all-news", "politics"]


def test_there_is_no_nature_item_even_for_a_nature_headline(project):
    setup(project)
    document = run(project, good_fetch())
    wolf = items_of(document)["betankande/vargen_hc01mju3"]
    assert wolf["title"] == "Betänkande om skydd av vargen och naturreservat"
    assert wolf["topics"] == ["all-news", "politics"]
    assert all("nature" not in i["topics"] for i in document["items"])
    feeds = source_entry(document, "riksdagen")["feeds"]
    assert [f["topic"] for f in feeds] == ["all-news", "politics", "ai"]
    assert [f["itemCount"] for f in feeds] == [6, 6, 1]


def test_budget_items_with_the_same_number_are_distinct_items(project):
    # Duplicates are removed by normalised link (R5.3), not by title or number: the budget
    # propositions share "prop. 2026/27:1" but have different titles and links.
    setup(project)
    items = items_of(run(project, good_fetch()))
    one = items["proposition/budgetpropositionen-for-2027_hc031-uo1"]
    two = items["proposition/budgetpropositionen-for-2027_hc031-uo2"]
    assert one["id"] != two["id"]
    assert one["title"] == "Budgetpropositionen för 2027 – Utgiftsområde 1 Rikets styrelse"
    assert two["title"].endswith("Utgiftsområde 2 Samhällsekonomi")


def test_the_same_link_twice_is_still_one_item(project):
    setup(project)
    link = BASE + "proposition/x_hc1"
    body = feed(("Första rubriken", link, "Fri, 13 Nov 2026 10:00:00 +0200"),
                ("Andra rubriken", link + "?a=1", "Fri, 13 Nov 2026 09:00:00 +0200"))
    items = run(project, good_fetch(body))["items"]
    assert [i["title"] for i in items] == ["Första rubriken"]


def test_titles_are_cleaned_and_never_cut(project):
    setup(project)
    items = items_of(run(project, good_fetch()))
    assert items["betankande/ai-i-offentlig-sektor_hc01ku4"]["title"] == "Betänkande om AI i offentlig sektor"
    long_title = "Betänkande " + "mycket långt ".join([""] * 40) + "slut"
    body = feed((long_title, BASE + "betankande/long_hc1", "Fri, 13 Nov 2026 10:00:00 +0200"))
    assert run(project, good_fetch(body))["items"][0]["title"] == " ".join(long_title.split())


def test_description_author_guid_and_images_never_reach_the_output(project):
    setup(project)
    run(project, good_fetch())
    text = (project.out / "news.json").read_text(encoding="utf-8")
    for forbidden in ("prop. 2026/27", "bild-exempel", "logo-exempel", "riksdagsinformation",
                      "data.riksdagen.se", ".png", "Handlar om artificiell"):
        assert forbidden not in text


def test_the_parser_reads_only_title_link_and_pubdate_of_the_items():
    entries = parse_rss(SAMPLE)
    assert len(entries) == 6
    assert entries[0].link == BASE + "proposition/exempelproposition-om-skatt_hc0310"
    assert entries[0].time_text == "Fri, 13 Nov 2026 10:17:04 +0200"
    assert not any("riksdagsinformation" in e.title + e.link + e.time_text for e in entries)


# ---- the real file ------------------------------------------------------

def test_the_real_file_has_riksdagen_disabled_so_it_is_not_fetched(project, tmp_path):
    # R16.9: F7 changes this test to `enabled` true, together with the credit text on the page.
    sources = json.loads((APP / "sources.json").read_text(encoding="utf-8"))["sources"]
    assert next(s for s in sources if s["id"] == "riksdagen")["enabled"] is False
    fetch = FakeFetch({"https://www.svt.se/robots.txt": ROBOTS_OK,
                       ROBOTS: NOT_FOUND, FEED_URL: SAMPLE})
    document = build(tmp_path / "out", NOW, fetch)  # the project's own sources.json
    assert all(s["id"] != "riksdagen" for s in document["sources"])
    assert all(s["sourceId"] != "riksdagen" for s in document["items"])
    assert all("riksdagen" not in call for call in fetch.calls)


# ---- failure isolation --------------------------------------------------

BAD_RESPONSES = {
    "malformed": b"<rss version='2.0'><channel><item><title>x</title></channel>",
    "not rss": b"<html><body>Tekniskt fel</body></html>",
    "empty body": b"",
    "no items": feed(),
    "oversized": b"<rss><channel>" + b"x" * (MAX_RESPONSE_BYTES + 1) + b"</channel></rss>",
    "http 500": FetchError("status", "HTTP status 500", 500),
    "timeout": FetchError("timeout", "timed out"),
    "unexpected exception": RuntimeError("boom"),
}


@pytest.mark.parametrize("name", list(BAD_RESPONSES))
def test_a_bad_riksdagen_response_fails_only_riksdagen(project, name):
    sources = json.loads((APP / "sources.json").read_text(encoding="utf-8"))["sources"]
    svt = next(s for s in sources if s["id"] == "svt")
    project.write_sources(svt, real_riksdagen())
    svt_body = feed(("Exempelnyhet från SVT", "https://www.svt.se/nyheter/inrikes/a",
                     "Fri, 13 Nov 2026 11:00:00 GMT"))
    fetch = FakeFetch({"https://www.svt.se/robots.txt": ROBOTS_OK, ROBOTS: NOT_FOUND,
                       "https://www.svt.se/nyheter/rss.xml": svt_body,
                       "https://www.svt.se/nyheter/inrikes/rss.xml": svt_body,
                       FEED_URL: BAD_RESPONSES[name]})
    document = run(project, fetch)
    assert source_entry(document, "svt")["status"] == "ok"
    assert source_entry(document, "riksdagen")["status"] == "error"
    assert [f["status"] for f in source_entry(document, "riksdagen")["feeds"]] == ["error"] * 3
    assert {i["sourceId"] for i in document["items"]} == {"svt"}
    assert "Tekniskt fel" not in json.dumps(document)


def test_a_failed_riksdagen_fetch_keeps_the_previous_riksdagen_items_for_24_hours(project):
    setup(project)
    run(project, good_fetch())
    later = NOW.replace(hour=14)
    failing = FakeFetch({ROBOTS: NOT_FOUND, FEED_URL: FetchError("timeout", "timed out")})
    document = run(project, failing, now=later)
    assert source_entry(document, "riksdagen")["status"] == "error"
    assert len(document["items"]) == 6  # the fallback (R19.4) applies the link rule again


# ---- hostile links (R9.1, R16.2) ---------------------------------------

HOSTILE = [
    "https://data.riksdagen.se/dokument/hc0310",
    "https://riksdagen.se/sv/dokument-och-lagar/dokument/a",
    "https://docs.riksdagen.se/a",
    "https://www.riksdagen.se.evil.example.org/a",
    "https://evil.example.org/www.riksdagen.se/a",
    "https://www.riksdagen.se@evil.example.org/a",
    "https://www.riksdagen.se:8443/a",
    "https://www.riksdagen.se\\@evil.example.org/a",
    "https://notwww.riksdagen.se/a",
    "https://wwwriksdagen.se/a",
    "javascript:alert(1)",
    "JaVaScRiPt://www.riksdagen.se/%0aalert(1)",
    "data:text/html,<b>x</b>",
    "ftp://www.riksdagen.se/a",
    "//www.riksdagen.se/a",
    "www.riksdagen.se/a",
    "/sv/dokument-och-lagar/dokument/a",
    "",
]


@pytest.mark.parametrize("link", HOSTILE)
def test_links_on_other_hosts_or_schemes_are_dropped(project, link):
    setup(project)
    good = BASE + "proposition/ok_hc1"
    body = feed(("Hotfull rubrik", link, "Fri, 13 Nov 2026 11:00:00 +0200"),
                ("Fin rubrik", good, "Fri, 13 Nov 2026 10:00:00 +0200"))
    document = run(project, good_fetch(body))
    assert [i["url"] for i in document["items"]] == [good]


def test_link_hosts_must_match_exactly_but_the_scheme_and_case_follow_r9_1():
    allowed, link_hosts = ["riksdagen.se"], ["www.riksdagen.se"]
    assert check_url("https://www.riksdagen.se/a/b/", allowed, link_hosts) == "https://riksdagen.se/a/b"
    assert check_url("https://WWW.Riksdagen.SE/a", allowed, link_hosts) == "https://riksdagen.se/a"
    assert check_url("https://data.riksdagen.se/a", allowed, link_hosts) is None
    assert check_url("https://riksdagen.se/a", allowed, link_hosts) is None
    # Without linkHosts a subdomain is fine, as for every other source (R9.1).
    assert check_url("https://data.riksdagen.se/a", allowed) == "https://data.riksdagen.se/a"
    # linkHosts never widens allowedHosts.
    assert check_url("https://www.example.org/a", allowed, ["www.example.org"]) is None


def test_a_previous_item_on_the_wrong_host_is_not_kept_by_the_fallback(project):
    setup(project)
    run(project, good_fetch())
    news = json.loads((project.out / "news.json").read_text(encoding="utf-8"))
    news["items"][0]["url"] = "https://data.riksdagen.se/dokument/hc0310"
    (project.out / "news.json").write_text(json.dumps(news), encoding="utf-8")
    failing = FakeFetch({ROBOTS: NOT_FOUND, FEED_URL: FetchError("timeout", "timed out")})
    document = run(project, failing, now=NOW.replace(hour=14))
    assert len(document["items"]) == 5
    assert all(i["url"].startswith(BASE) for i in document["items"])


# ---- time (R16.7) -------------------------------------------------------

def utc(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def test_winter_clock_time_is_stockholm_time_not_the_wrong_plus_0200():
    text = "Fri, 13 Nov 2026 10:17:04 +0200"
    assert parse_time(text, local_clock=True) == utc("2026-11-13T09:17:04Z")
    assert parse_time(text) == utc("2026-11-13T08:17:04Z")  # without the option the offset is trusted
    published = published_utc(text, NOW, local_clock=True)
    assert published == "2026-11-13T09:17:04Z"
    assert display_time(published) == "2026-11-13 10:17"  # the clock digits of the feed


def test_summer_clock_time_is_stockholm_time_and_agrees_with_the_offset():
    text = "Mon, 15 Jun 2026 10:00:00 +0200"
    assert parse_time(text, local_clock=True) == utc("2026-06-15T08:00:00Z")
    assert parse_time(text) == utc("2026-06-15T08:00:00Z")
    now = utc("2026-06-15T12:00:00Z")
    assert published_utc(text, now, local_clock=True) == "2026-06-15T08:00:00Z"
    assert display_time("2026-06-15T08:00:00Z") == "2026-06-15 10:00"


@pytest.mark.parametrize("zone", ["+0200", "+0100", "-0500", "GMT", "UT", "Z", "EST", "", " +0000"])
def test_the_stated_zone_is_ignored_with_local_clock(zone):
    text = ("Fri, 13 Nov 2026 10:17:04 " + zone).rstrip()
    assert parse_time(text, local_clock=True) == utc("2026-11-13T09:17:04Z")


def test_local_clock_also_reads_iso_text_and_the_switch_hours_follow_the_general_rules():
    assert parse_time("2026-11-13T10:17:04+02:00", local_clock=True) == utc("2026-11-13T09:17:04Z")
    assert parse_time("Sun, 29 Mar 2026 02:30:00 +0200", local_clock=True) == utc("2026-03-29T01:30:00Z")
    assert parse_time("Sun, 25 Oct 2026 02:30:00 +0200", local_clock=True) == utc("2026-10-25T00:30:00Z")


@pytest.mark.parametrize("text", ["", "not a date", "Fri, 32 Nov 2026 10:00:00 +0200",
                                  "Fri, 13 Nov 2026 25:00:00 +0200", "Fri, 13 Foo 2026 10:00:00 +0200"])
def test_local_clock_still_refuses_unusable_text(text):
    assert parse_time(text, local_clock=True) is None


def test_the_build_reads_the_riksdag_dates_as_stockholm_time(project):
    setup(project)
    items = items_of(run(project, good_fetch()))
    one = items["proposition/exempelproposition-om-skatt_hc0310"]
    assert one["published"] == "2026-11-13T09:17:04Z" and one["publishedDisplay"] == "2026-11-13 10:17"
    assert items["betankande/ai-i-offentlig-sektor_hc01ku4"]["published"] == "2026-11-11T13:30:00Z"


def test_the_build_reads_a_summer_date_as_stockholm_time(project):
    setup(project)
    now = utc("2026-06-15T12:00:00Z")
    body = feed(("Sommarbetänkande", BASE + "betankande/sommar_hc1", "Mon, 15 Jun 2026 10:00:00 +0200"))
    item = run(project, good_fetch(body), now=now)["items"][0]
    assert item["published"] == "2026-06-15T08:00:00Z"
    assert item["publishedDisplay"] == "2026-06-15 10:00"


def test_other_sources_keep_trusting_the_offset(project):
    # The option is per source: a source without `timeZone` reads +0200 as given.
    project.write_sources({k: v for k, v in real_riksdagen().items() if k != "timeZone"})
    item = run(project, good_fetch())["items"][0]
    assert item["published"] == "2026-11-13T08:17:04Z"
