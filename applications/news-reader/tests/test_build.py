"""The build command with a fake fetch layer: no network, invented feeds and hosts."""
import json
import runpy
import sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from newsreader import build as build_module
from newsreader import fetch as fetch_module
from newsreader.__main__ import main
from newsreader.build import BuildError, build
from newsreader.fetch import FetchError
from newsreader.parse import MAX_RESPONSE_BYTES
from tests.fakes import (BROWSER_FEED_URL, FEED_URL, GOOD_FEED, NOW, ROBOTS_URL, FakeFetch,
                            APP, browser_source, politics, rss, source)

ITEM_FIELDS_V1 = {"id", "sourceId", "sourceName", "title", "url", "published", "publishedDisplay"}
ITEM_FIELDS = ITEM_FIELDS_V1 | {"topics"}  # R1.5
ROBOTS_OK = b"User-agent: *\nAllow: /\n"


def run(project, fetch, now=NOW, **kwargs):
    return build(project.out, now, fetch, root=project.root, **kwargs)


def read_news(project):
    return json.loads((project.out / "news.json").read_text(encoding="utf-8"))


def source_entry(document, source_id="test-news"):
    return next(s for s in document["sources"] if s["id"] == source_id)


# --- success path -----------------------------------------------------------

def test_success_writes_expected_news_json(project):
    fetch = FakeFetch({ROBOTS_URL: ROBOTS_OK, FEED_URL: GOOD_FEED})
    document = run(project, fetch)
    assert read_news(project) == document
    assert document["version"] == 2
    assert "category" not in document
    assert document["topics"] == ["all-news", "politics", "nature", "ai"]
    assert document["generatedAt"] == "2026-11-13T12:00:00Z"
    assert document["generatedAtDisplay"] == "2026-11-13 13:00"
    assert document["sources"] == [{
        "id": "test-news", "name": "Test News", "status": "ok",
        "lastSuccess": "2026-11-13T12:00:00Z", "itemCount": 2,
        "feeds": [{"topic": "politics", "status": "ok", "lastSuccess": "2026-11-13T12:00:00Z", "itemCount": 2}]}]
    titles = [i["title"] for i in document["items"]]
    assert titles == ["Riksdagen debatterar exempelfrågan", "Regeringen presenterar ett påhittat förslag"]
    first = document["items"][0]
    assert set(first) == ITEM_FIELDS
    assert first["sourceId"] == "test-news" and first["sourceName"] == "Test News"
    assert first["published"] == "2026-11-13T11:00:00Z"
    assert first["publishedDisplay"] == "2026-11-13 12:00"
    assert first["url"] == "https://news.example.invalid/a/1"
    assert first["topics"] == ["politics"]


def test_news_json_is_utf8_with_swedish_letters(project):
    run(project, FakeFetch({FEED_URL: GOOD_FEED}))
    text = (project.out / "news.json").read_bytes().decode("utf-8")
    assert "påhittat" in text and "\\u00e5" not in text


def test_one_request_per_feed_and_one_robots_read(project):
    fetch = FakeFetch({ROBOTS_URL: ROBOTS_OK, FEED_URL: GOOD_FEED})
    project.write_sources(source(), source(id="second", name="Second",
                                           feeds=politics("https://news.example.invalid/other.xml", "keywordFilter")))
    fetch.responses["https://news.example.invalid/other.xml"] = GOOD_FEED
    run(project, fetch)
    assert fetch.calls.count(ROBOTS_URL) == 1
    assert fetch.calls.count(FEED_URL) == 1
    assert fetch.calls.count("https://news.example.invalid/other.xml") == 1


def test_output_folder_has_the_copied_files(project):
    run(project, FakeFetch({FEED_URL: GOOD_FEED}))
    out = project.out
    assert (out / "logic.js").read_bytes() == (project.root / "site" / "logic.js").read_bytes()
    assert not (out / "tests").exists()  # site/tests is not copied
    for name in ("sources.json", "politics-keywords.json", "nature-keywords.json", "ai-keywords.json"):
        assert (out / name).read_bytes() == (project.root / name).read_bytes()  # R14.5
    assert (out / "news.json").exists()


def test_site_content_is_copied_without_tests_and_cache_folders(project):
    (project.root / "site" / "css").mkdir()
    (project.root / "site" / "css" / "a.css").write_text("x", encoding="utf-8")
    (project.root / "site" / "__pycache__").mkdir()
    (project.root / "site" / "__pycache__" / "z.pyc").write_bytes(b"x")
    (project.root / "site" / "css" / "tests").mkdir()  # only the top-level tests folder is skipped
    (project.root / "site" / "css" / "tests" / "b.css").write_text("y", encoding="utf-8")
    run(project, FakeFetch({FEED_URL: GOOD_FEED}))
    assert (project.out / "css" / "a.css").exists() and (project.out / "css" / "tests" / "b.css").exists()
    assert not (project.out / "__pycache__").exists() and not (project.out / "tests").exists()


def test_running_twice_is_repeatable(project):
    fetch = FakeFetch({FEED_URL: GOOD_FEED})
    run(project, fetch)
    first = {p.relative_to(project.out): p.read_bytes() for p in project.out.rglob("*") if p.is_file()}
    run(project, fetch)
    second = {p.relative_to(project.out): p.read_bytes() for p in project.out.rglob("*") if p.is_file()}
    assert first == second
    assert not list(project.out.glob("*.tmp"))


# --- failing sources and the 24-hour fallback -----------------------------

def previous_file(path, last_success, status="ok", extra_items=()):
    items = [{
        "id": "0123456789abcdef", "sourceId": "test-news", "sourceName": "Test News",
        "title": "Gammal riksdagsrubrik", "url": "https://news.example.invalid/old/1",
        "published": "2026-11-13T01:00:00Z", "publishedDisplay": "2026-11-13 02:00"}, *extra_items]
    document = {"version": 1, "generatedAt": last_success, "generatedAtDisplay": "x", "category": "politics-sweden",
                "sources": [{"id": "test-news", "name": "Test News", "status": status,
                             "lastSuccess": last_success, "itemCount": len(items)}],
                "items": items}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def failing():
    return FakeFetch({FEED_URL: FetchError("network", "network error")})


def test_failing_source_without_previous_file(project):
    document = run(project, failing())
    assert document["items"] == []
    entry = source_entry(document)
    assert entry["status"] == "error" and entry["lastSuccess"] is None and entry["itemCount"] == 0
    assert "network error" in entry["message"]
    assert read_news(project) == document  # the build still writes everything
    assert (project.out / "logic.js").exists()


def test_failing_source_keeps_previous_items_within_24_hours(project):
    last = NOW - timedelta(hours=23, minutes=59)
    previous_file(project.out / "news.json", last.strftime("%Y-%m-%dT%H:%M:%SZ"))
    document = run(project, failing())
    entry = source_entry(document)
    assert entry["status"] == "error"
    assert entry["lastSuccess"] == last.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert entry["itemCount"] == 1
    assert [i["title"] for i in document["items"]] == ["Gammal riksdagsrubrik"]
    assert set(document["items"][0]) == ITEM_FIELDS
    assert document["items"][0]["topics"] == ["politics"]  # a version 1 file: its items are politics (R19.4)


def test_failing_source_drops_previous_items_at_24_hours(project):
    last = NOW - timedelta(hours=24)
    previous_file(project.out / "news.json", last.strftime("%Y-%m-%dT%H:%M:%SZ"))
    document = run(project, failing())
    entry = source_entry(document)
    assert document["items"] == []
    assert entry["status"] == "error" and entry["itemCount"] == 0
    assert entry["lastSuccess"] == last.strftime("%Y-%m-%dT%H:%M:%SZ")  # still tells when it last worked


def test_fallback_window_is_counted_from_the_last_success_not_the_last_build(project):
    # The previous build already failed once: its file says error, last success 20 hours ago.
    last = NOW - timedelta(hours=20)
    previous_file(project.out / "news.json", last.strftime("%Y-%m-%dT%H:%M:%SZ"), status="error")
    document = run(project, failing())
    assert document["sources"][0]["lastSuccess"] == last.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert len(document["items"]) == 1


def test_previous_items_that_break_the_rules_are_not_kept(project):
    last = (NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    bad = [
        {"id": "a", "sourceId": "test-news", "sourceName": "x", "title": "Andra värden", "url": "https://evil.example.org/x",
         "published": None, "publishedDisplay": "Tid saknas"},
        {"id": "b", "sourceId": "other", "sourceName": "x", "title": "Annan källa", "url": "https://news.example.invalid/x",
         "published": None, "publishedDisplay": "Tid saknas"},
        {"id": "c", "sourceId": "test-news", "title": "Extra fält saknas", "url": "https://news.example.invalid/y"},
    ]
    previous_file(project.out / "news.json", last, extra_items=bad)
    document = run(project, failing())
    assert [i["title"] for i in document["items"]] == ["Gammal riksdagsrubrik"]


def test_previous_override(project, tmp_path):
    last = (NOW - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    previous_file(tmp_path / "elsewhere" / "prev.json", last)
    document = run(project, failing(), previous_path=tmp_path / "elsewhere" / "prev.json")
    assert len(document["items"]) == 1
    # without the override, <out>/news.json does not exist, so there is no fallback
    project.out.joinpath("news.json").unlink()
    assert run(project, failing())["items"] == []


def test_default_previous_is_the_output_news_json_and_is_read_before_overwriting(project):
    run(project, FakeFetch({FEED_URL: GOOD_FEED}), now=NOW - timedelta(hours=3))
    document = run(project, failing())  # the second build fails; the first one's items come back
    entry = source_entry(document)
    assert entry["status"] == "error" and entry["itemCount"] == 2
    assert entry["lastSuccess"] == "2026-11-13T09:00:00Z"
    assert read_news(project) == document


def test_unreadable_previous_file_is_ignored(project):
    project.out.mkdir()
    (project.out / "news.json").write_text("{not json", encoding="utf-8")
    assert run(project, failing())["items"] == []


@pytest.mark.parametrize("response", [
    FetchError("status", "HTTP status 500", 500),
    FetchError("timeout", "timeout"),
    FetchError("too-large", "response larger than 2 MB"),
    FetchError("redirect", "redirect to a host that is not allowed"),
    RuntimeError("unexpected"),
    b"<html>not a feed</html>",
    b"<rss version='2.0'><channel></channel></rss>",  # zero items
    b"",
])
def test_every_kind_of_failure_is_a_failed_source_not_a_failed_build(project, response):
    document = run(project, FakeFetch({FEED_URL: response}))
    entry = source_entry(document)
    assert entry["status"] == "error" and entry["message"]
    assert document["items"] == []


def test_oversized_response_through_the_parser_limit(project):
    big = b"<rss>" + b" " * MAX_RESPONSE_BYTES + b"</rss>"
    document = run(project, FakeFetch({FEED_URL: big}))
    assert source_entry(document)["status"] == "error"


def test_zero_parsed_items_counts_as_failed_and_falls_back(project):
    previous_file(project.out / "news.json", (NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    empty = b"<rss version='2.0'><channel><title>x</title></channel></rss>"
    document = run(project, FakeFetch({FEED_URL: empty}))
    assert source_entry(document)["status"] == "error"
    assert len(document["items"]) == 1


def test_items_all_filtered_out_is_still_ok(project):
    quiet = rss(("Vädret blir fint", "/a/9", "Fri, 13 Nov 2026 11:00:00 GMT"))
    document = run(project, FakeFetch({FEED_URL: quiet}))
    entry = source_entry(document)
    assert entry["status"] == "ok" and entry["itemCount"] == 0


def test_category_filter_source_is_marked_failed_with_a_message(project):
    project.write_sources(source(feeds=politics(FEED_URL, "categoryFilter")))
    document = run(project, FakeFetch({FEED_URL: GOOD_FEED}))
    entry = source_entry(document)
    assert entry["status"] == "error"
    assert "categoryFilter" in entry["message"] and "selection failed" in entry["message"]
    assert "ValueError" in entry["message"]
    assert document["items"] == []


def test_one_failing_source_does_not_stop_the_other(project):
    other = "https://news.example.invalid/other.xml"
    project.write_sources(source(), source(id="second", name="Second",
                                           feeds=politics(other, "keywordFilter")))
    document = run(project, FakeFetch({FEED_URL: RuntimeError("x"), other: GOOD_FEED}))
    assert [s["status"] for s in document["sources"]] == ["error", "ok"]
    assert {i["sourceId"] for i in document["items"]} == {"second"}


# --- robots.txt, enabled, browser sources --------------------------------

def test_robots_disallow_blocks_the_fetch(project):
    fetch = FakeFetch({ROBOTS_URL: b"User-agent: *\nDisallow: /politics/\n", FEED_URL: GOOD_FEED})
    document = run(project, fetch)
    entry = source_entry(document)
    assert entry["status"] == "blocked-by-robots" and entry["itemCount"] == 0
    assert FEED_URL not in fetch.calls
    assert document["items"] == []


def test_robots_block_does_not_keep_previous_items(project):
    previous_file(project.out / "news.json", (NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    fetch = FakeFetch({ROBOTS_URL: b"User-agent: *\nDisallow: /\n", FEED_URL: GOOD_FEED})
    assert run(project, fetch)["items"] == []


def test_robots_uses_our_own_user_agent_group(project):
    robots = b"User-agent: *\nDisallow: /\n\nUser-agent: GithubAutoPlay-news-reader\nAllow: /\n"
    document = run(project, FakeFetch({ROBOTS_URL: robots, FEED_URL: GOOD_FEED}))
    assert source_entry(document)["status"] == "ok"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 451])
def test_robots_4xx_means_no_rules_and_allowed(project, status):
    robots = FetchError("status", "HTTP status %d" % status, status)
    fetch = FakeFetch({ROBOTS_URL: robots, FEED_URL: GOOD_FEED})
    document = run(project, fetch)
    assert source_entry(document)["status"] == "ok"
    assert FEED_URL in fetch.calls


@pytest.mark.parametrize("robots", [
    FetchError("timeout", "timeout"),
    FetchError("network", "network error"),
    FetchError("status", "HTTP status 500", 500),
    FetchError("status", "HTTP status 503", 503),
    FetchError("status", "HTTP status 429", 429),
    FetchError("too-large", "response larger than 2 MB"),
    FetchError("redirect", "redirect to a host that is not allowed"),
    RuntimeError("boom"),
    b"\xff\xfe garbage",
])
def test_unreadable_robots_means_not_fetched_and_status_error(project, robots):
    fetch = FakeFetch({ROBOTS_URL: robots, FEED_URL: GOOD_FEED})
    document = run(project, fetch)
    entry = source_entry(document)
    assert entry["status"] == "error" and "robots.txt could not be read" in entry["message"]
    assert FEED_URL not in fetch.calls
    assert document["items"] == []


@pytest.mark.parametrize("robots", [FetchError("timeout", "timeout"), FetchError("status", "HTTP status 500", 500)])
def test_unreadable_robots_uses_the_24_hour_fallback(project, robots):
    last = (NOW - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    previous_file(project.out / "news.json", last)
    document = run(project, FakeFetch({ROBOTS_URL: robots, FEED_URL: GOOD_FEED}))
    entry = source_entry(document)
    assert entry["status"] == "error" and entry["lastSuccess"] == last and entry["itemCount"] == 1
    assert [i["title"] for i in document["items"]] == ["Gammal riksdagsrubrik"]


def test_unreadable_robots_older_than_24_hours_drops_previous_items(project):
    previous_file(project.out / "news.json", (NOW - timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    document = run(project, FakeFetch({ROBOTS_URL: FetchError("timeout", "timeout"), FEED_URL: GOOD_FEED}))
    assert document["items"] == [] and source_entry(document)["status"] == "error"


def test_unreadable_robots_is_read_once_for_all_sources_of_the_host(project):
    other = "https://news.example.invalid/other.xml"
    project.write_sources(source(), source(id="second", name="Second",
                                           feeds=politics(other, "keywordFilter")))
    fetch = FakeFetch({ROBOTS_URL: FetchError("timeout", "timeout"), FEED_URL: GOOD_FEED, other: GOOD_FEED})
    document = run(project, fetch)
    assert [s["status"] for s in document["sources"]] == ["error", "error"]
    assert fetch.calls == [ROBOTS_URL]


def test_robots_is_checked_before_the_feed_is_requested(project):
    fetch = FakeFetch({FEED_URL: GOOD_FEED})
    run(project, fetch)
    assert fetch.calls == [ROBOTS_URL, FEED_URL]


def test_disabled_source_is_not_fetched_and_not_listed(project):
    project.write_sources(source(enabled=False))
    fetch = FakeFetch({ROBOTS_URL: ROBOTS_OK, FEED_URL: GOOD_FEED})
    document = run(project, fetch)
    assert fetch.calls == []
    assert document["sources"] == [] and document["items"] == []


def test_disabled_source_previous_items_are_not_carried_over(project):
    previous_file(project.out / "news.json", (NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    project.write_sources(source(enabled=False))
    assert run(project, FakeFetch())["items"] == []


def test_browser_source_is_skipped_and_never_listed(project):
    fetch = FakeFetch({FEED_URL: GOOD_FEED, BROWSER_FEED_URL: rss(
        ("Riksdagen i direktsändning", "/live/1", "Fri, 13 Nov 2026 11:00:00 GMT"))})
    document = run(project, fetch)
    assert BROWSER_FEED_URL not in fetch.calls
    assert not any("live.example.invalid" in c for c in fetch.calls)
    assert [s["id"] for s in document["sources"]] == ["test-news"]
    assert all(i["sourceId"] == "test-news" for i in document["items"])


def test_real_sources_json_the_build_never_requests_sveriges_radio(project, tmp_path):
    svt_feed = rss(("Riksdagen röstar om ett påhittat ärende", "/x", "Fri, 13 Nov 2026 11:00:00 GMT")
                   ).replace(b"news.example.invalid", b"www.svt.se")
    fetch = FakeFetch({"https://www.svt.se/robots.txt": ROBOTS_OK,
                       "https://www.svt.se/nyheter/rss.xml": svt_feed,
                       "https://www.svt.se/nyheter/inrikes/rss.xml": svt_feed,
                       "https://api.sr.se/api/rss/program/83": rss(
                           ("Riksdagen hos Ekot påhittad", "/artikel/1", "Fri, 13 Nov 2026 11:00:00 GMT"))})
    out = tmp_path / "real-out"
    document = build(out, NOW, fetch)  # the project's own sources.json
    assert [s["id"] for s in document["sources"]] == ["svt"]
    assert all("api.sr.se" not in c and "sverigesradio" not in c for c in fetch.calls)
    assert document["items"] and all(i["sourceId"] == "svt" for i in document["items"])
    for path in out.rglob("*"):
        if path.is_file():
            assert "Ekot" not in path.read_text(encoding="utf-8", errors="ignore")


def test_sveriges_radio_like_source_fetched_by_mistake_is_refused(project, monkeypatch):
    # Pretend the filter that skips browser sources is broken: the guards must still refuse.
    sr_headline = "Riksdagen enligt Ekot (påhittad rubrik)"
    fetch = FakeFetch({BROWSER_FEED_URL: rss((sr_headline, "/artikel/7", "Fri, 13 Nov 2026 11:00:00 GMT")),
                       FEED_URL: GOOD_FEED})
    monkeypatch.setattr(build_module, "build_sources", lambda sources: list(sources))
    with pytest.raises(BuildError, match="refusing"):
        run(project, fetch)
    assert BROWSER_FEED_URL not in fetch.calls
    assert not project.out.exists()  # nothing was written


def test_assert_storable_refuses_browser_and_not_stored_sources():
    for bad in (browser_source(), source(storageAllowed=False), source(fetchedBy="browser")):
        with pytest.raises(BuildError):
            build_module.assert_storable(bad)
    build_module.assert_storable(source())


def test_final_guard_refuses_an_item_of_a_browser_source():
    topics = ["all-news", "politics", "nature", "ai"]
    document = {"sources": [{"id": "test-news"}],
                "items": [{"sourceId": "live-radio", "title": "Riksdagen (påhittad)"}]}
    with pytest.raises(BuildError, match="refusing"):
        build_module._check_document(document, [source(), browser_source()], topics)
    document = {"sources": [{"id": "live-radio"}], "items": []}
    with pytest.raises(BuildError, match="refusing"):
        build_module._check_document(document, [source(), browser_source()], topics)


# --- invalid configuration -------------------------------------------------

def test_invalid_sources_json_fails_and_writes_nothing(project):
    (project.root / "sources.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(BuildError, match="sources.json"):
        run(project, FakeFetch())
    assert not project.out.exists()


@pytest.mark.parametrize("change", [
    {"fetchedBy": "elsewhere"},
    {"enabled": "yes"},
    {"id": ""},
    {"allowedHosts": []},
    {"feeds": politics(FEED_URL, "magic")},
    {"feeds": politics("http://news.example.invalid/x")},
    {"feeds": politics("https://other.example.org/x")},
    {"storageAllowed": False},  # a build source must be storable
])
def test_invalid_source_entries_fail(project, change):
    project.write_sources(source(**change))
    with pytest.raises(BuildError, match="sources.json"):
        run(project, FakeFetch())


def test_browser_source_that_may_be_stored_is_invalid(project):
    project.write_sources(source(), browser_source(storageAllowed=True))
    with pytest.raises(BuildError, match="storageAllowed false"):
        run(project, FakeFetch())


def test_duplicate_source_ids_and_empty_list_fail(project):
    project.write_sources(source(), source())
    with pytest.raises(BuildError, match="duplicate"):
        run(project, FakeFetch())
    project.write_sources()
    with pytest.raises(BuildError):
        run(project, FakeFetch())


def test_invalid_keywords_file_fails_and_writes_nothing(project):
    (project.root / "politics-keywords.json").write_text('{"version": 2}', encoding="utf-8")
    with pytest.raises(BuildError, match="politics-keywords.json"):
        run(project, FakeFetch())
    assert not project.out.exists()


def test_missing_keywords_file_fails(project):
    (project.root / "politics-keywords.json").unlink()
    with pytest.raises(BuildError, match="politics-keywords.json: file not found"):
        run(project, FakeFetch())
    assert not project.out.exists()


@pytest.mark.parametrize("name", ["nature-keywords.json", "ai-keywords.json"])
def test_missing_or_invalid_keyword_file_of_another_topic_fails_even_if_no_source_uses_it(project, name):
    # R14.5, R17.5: every file named in sources.json is loaded, not only those a feed needs.
    (project.root / name).write_text('{"version": 2}', encoding="utf-8")
    with pytest.raises(BuildError, match=name):
        run(project, FakeFetch())
    (project.root / name).unlink()
    with pytest.raises(BuildError, match=name + ": file not found"):
        run(project, FakeFetch())
    assert not project.out.exists()


def test_a_keyword_file_for_the_wrong_topic_fails(project):
    # The file named for ai holds the politics list: its topic does not match (R17.5).
    (project.root / "ai-keywords.json").write_bytes((project.root / "politics-keywords.json").read_bytes())
    with pytest.raises(BuildError, match="ai-keywords.json: topic must be 'ai'"):
        run(project, FakeFetch())


def test_the_real_keyword_files_all_load():
    topics, _ = build_module.load_configuration(APP / "sources.json")
    keywords = build_module.load_keyword_files(APP, topics)
    assert sorted(keywords) == ["ai", "nature", "politics"]


@pytest.mark.parametrize("where", ["", "site"])
def test_output_folder_may_not_overlap_the_project(project, where):
    target = project.root / where if where else project.root
    with pytest.raises(BuildError, match="overlaps"):
        build(target, NOW, FakeFetch(), root=project.root)


# --- the command line entry ---------------------------------------------

def test_cli_end_to_end_with_injected_fetch(project, capsys):
    fetch = FakeFetch({ROBOTS_URL: ROBOTS_OK, FEED_URL: GOOD_FEED})
    code = main(["--out", str(project.out)], fetch=fetch, now=NOW, root=project.root)
    assert code == 0
    assert read_news(project)["sources"][0]["itemCount"] == 2
    assert "test-news: ok, 2 items" in capsys.readouterr().out


def test_cli_previous_option(project, tmp_path):
    last = (NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    previous_file(tmp_path / "prev.json", last)
    code = main(["--out", str(project.out), "--previous", str(tmp_path / "prev.json")],
                fetch=failing(), now=NOW, root=project.root)
    assert code == 0
    assert read_news(project)["items"][0]["title"] == "Gammal riksdagsrubrik"


def test_cli_failing_source_still_exits_zero(project, capsys):
    assert main(["--out", str(project.out)], fetch=failing(), now=NOW, root=project.root) == 0
    assert "test-news: error" in capsys.readouterr().out


def test_cli_invalid_configuration_exits_non_zero_with_message_on_stderr(project, capsys):
    (project.root / "sources.json").write_text("[]", encoding="utf-8")
    assert main(["--out", str(project.out)], fetch=FakeFetch(), now=NOW, root=project.root) == 1
    captured = capsys.readouterr()
    assert "build failed" in captured.err and "sources.json" in captured.err
    assert captured.out == ""


def test_cli_requires_out(capsys):
    with pytest.raises(SystemExit) as info:
        main([], fetch=FakeFetch())
    assert info.value.code == 2


def test_python_dash_m_entry_point_with_the_projects_own_files(tmp_path, monkeypatch, capsys):
    """Runs `python -m newsreader --out <dir>` through runpy, with the real fetch layer replaced."""
    # This path reads the real clock (datetime.now in __main__), so the article is dated
    # relative to the current time; a fixed date would fall out of the 7-day window (R5.2).
    recent = format_datetime(datetime.now(timezone.utc) - timedelta(hours=1), usegmt=True)
    svt_feed = rss(("Regeringen och riksdagen i en påhittad fråga", "/nyheter/inrikes/exempel", recent)).replace(b"news.example.invalid", b"www.svt.se")
    fake = FakeFetch({"https://www.svt.se/nyheter/rss.xml": svt_feed,
                      "https://www.svt.se/nyheter/inrikes/rss.xml": svt_feed})
    monkeypatch.setattr(fetch_module, "fetch_url", fake)
    out = tmp_path / "build"
    monkeypatch.setattr(sys, "argv", ["newsreader", "--out", str(out)])
    monkeypatch.delitem(sys.modules, "newsreader.__main__", raising=False)
    with pytest.raises(SystemExit) as info:
        runpy.run_module("newsreader", run_name="__main__")
    assert info.value.code == 0
    document = json.loads((out / "news.json").read_text(encoding="utf-8"))
    assert [s["id"] for s in document["sources"]] == ["svt"]
    assert fake.calls == ["https://www.svt.se/robots.txt", "https://www.svt.se/nyheter/rss.xml",
                          "https://www.svt.se/nyheter/inrikes/rss.xml"]
    assert document["items"][0]["topics"] == ["all-news", "politics"]
    assert (out / "sources.json").read_bytes() == (APP / "sources.json").read_bytes()
    for name in ("politics-keywords.json", "nature-keywords.json", "ai-keywords.json", "logic.js"):
        assert (out / name).exists()
    printed = capsys.readouterr().out
    assert "svt: ok, 1 items" in printed and "  all-news: ok, 1 items" in printed


# --- review round 1 -----------------------------------------------------

def test_robots_with_a_byte_order_mark_is_still_read(project):
    robots = b"\xef\xbb\xbfUser-agent: *\nDisallow: /\n"
    fetch = FakeFetch({ROBOTS_URL: robots, FEED_URL: GOOD_FEED})
    document = run(project, fetch)
    assert source_entry(document)["status"] == "blocked-by-robots"
    assert FEED_URL not in fetch.calls


def test_fallback_items_respect_the_seven_day_limit(project):
    last = (NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def item(path, published, title):
        return {"id": "x", "sourceId": "test-news", "sourceName": "x", "title": title,
                "url": "https://news.example.invalid" + path, "published": published,
                "publishedDisplay": "x"}

    extra = [item("/o/1", (NOW - timedelta(days=7, seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ"), "För gammal"),
             item("/o/2", (NOW - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"), "Exakt sju dagar"),
             item("/o/3", None, "Utan tid")]
    previous_file(project.out / "news.json", last, extra_items=extra)
    document = run(project, failing())
    titles = [i["title"] for i in document["items"]]
    assert "För gammal" not in titles
    assert titles == ["Gammal riksdagsrubrik", "Exakt sju dagar", "Utan tid"]
    assert document["sources"][0]["itemCount"] == 3


SECRET = "SECRETFEEDTEXT"


@pytest.mark.parametrize("response", [
    '<?xml version="1.0" encoding="%s"?><rss/>' % SECRET,
    "<rss><channel><%s></channel></rss>" % SECRET,
    "<%s>" % SECRET,
    SECRET,
    "<!DOCTYPE x [<!ENTITY %s 'a'>]><rss/>" % SECRET,
    RuntimeError(SECRET),
    FetchError("network", "network error"),
])
def test_status_message_never_contains_feed_content(project, response):
    if isinstance(response, str):
        response = response.encode("utf-8")
    document = run(project, FakeFetch({FEED_URL: response}))
    entry = source_entry(document)
    assert entry["status"] == "error"
    assert SECRET not in json.dumps(document) and SECRET not in entry["message"]


def test_status_message_for_robots_never_contains_content(project):
    document = run(project, FakeFetch({ROBOTS_URL: RuntimeError(SECRET), FEED_URL: GOOD_FEED}))
    assert SECRET not in json.dumps(document)
    document = run(project, FakeFetch({ROBOTS_URL: SECRET.encode() + b"\xff", FEED_URL: GOOD_FEED}))
    assert SECRET not in json.dumps(document)


def test_ok_source_has_no_message_field(project):
    document = run(project, FakeFetch({FEED_URL: GOOD_FEED}))
    assert "message" not in source_entry(document)


def test_output_folder_given_by_an_indirect_path_cannot_point_at_site(project, tmp_path):
    for target in (project.root / "site" / ".." / "site", project.root / "." / "site" / "sub"):
        with pytest.raises(BuildError, match="overlaps"):
            build(target, NOW, FakeFetch(), root=project.root)
    link = tmp_path / "link-to-app"
    link.symlink_to(project.root, target_is_directory=True)
    for target in (link / "site", link, link / "site" / "sub"):
        with pytest.raises(BuildError):
            build(target, NOW, FakeFetch(), root=project.root)
    with pytest.raises(BuildError, match="overlaps"):  # a folder that holds the project
        build(tmp_path, NOW, FakeFetch(), root=project.root)
    assert not (project.root / "site" / "news.json").exists()


def test_output_folder_inside_the_project_is_fine(project):
    build(project.root / "build", NOW, FakeFetch({FEED_URL: GOOD_FEED}), root=project.root)
    assert (project.root / "build" / "news.json").exists()


def test_symlinked_output_folder_is_refused(project, tmp_path):
    real = tmp_path / "real-out"
    real.mkdir()
    project.out.symlink_to(real, target_is_directory=True)
    with pytest.raises(BuildError, match="symbolic link"):
        run(project, FakeFetch({FEED_URL: GOOD_FEED}))
    assert list(real.iterdir()) == []


@pytest.mark.parametrize("name", ["news.json", "news.json.tmp", "sources.json", "logic.js"])
def test_symlinked_targets_are_not_written_through(project, tmp_path, name):
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me", encoding="utf-8")
    project.out.mkdir()
    (project.out / name).symlink_to(victim)
    with pytest.raises(BuildError, match="symbolic link"):
        run(project, FakeFetch({FEED_URL: GOOD_FEED}))
    assert victim.read_text(encoding="utf-8") == "keep me"
    assert not (project.out / "politics-keywords.json").exists()  # nothing was written at all


def test_symlinked_folder_inside_the_output_is_not_written_through(project, tmp_path):
    (project.root / "site" / "css").mkdir()
    (project.root / "site" / "css" / "a.css").write_text("x", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    project.out.mkdir()
    (project.out / "css").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(BuildError, match="symbolic link"):
        run(project, FakeFetch({FEED_URL: GOOD_FEED}))
    assert list(elsewhere.iterdir()) == []


# --- review round 2 -----------------------------------------------------

def test_symlinked_site_folder_is_followed_for_the_overlap_check(project, tmp_path):
    real_site = tmp_path / "real-site"
    (project.root / "site").rename(real_site)
    (project.root / "site").symlink_to(real_site, target_is_directory=True)
    for target in (real_site, real_site / "new-folder", real_site / "a" / "b", project.root / "site" / "new"):
        with pytest.raises(BuildError, match="site/"):
            build(target, NOW, FakeFetch(), root=project.root)
    assert not (real_site / "news.json").exists() and not (real_site / "new-folder").exists()
    # a normal output folder still works, and the files of the linked site/ are copied
    run(project, FakeFetch({FEED_URL: GOOD_FEED}))
    assert (project.out / "logic.js").exists()


def test_new_output_folder_inside_site_is_refused(project):
    with pytest.raises(BuildError, match="site/"):
        build(project.root / "site" / "not-yet", NOW, FakeFetch(), root=project.root)
    assert not (project.root / "site" / "not-yet").exists()


@pytest.mark.parametrize("name", ["news.json", "logic.js", "sources.json"])
def test_hard_linked_targets_are_replaced_not_written_into(project, tmp_path, name):
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me", encoding="utf-8")
    project.out.mkdir()
    import os
    os.link(victim, project.out / name)
    run(project, FakeFetch({FEED_URL: GOOD_FEED}))
    assert victim.read_text(encoding="utf-8") == "keep me"
    assert (project.out / name).read_text(encoding="utf-8") != "keep me"
    assert not list(project.out.glob("*.tmp"))


def test_file_symlinks_inside_site_are_not_followed(project, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("private", encoding="utf-8")
    (project.root / "site" / "link.txt").symlink_to(secret)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "inner.txt").write_text("private", encoding="utf-8")
    (project.root / "site" / "linked-dir").symlink_to(elsewhere, target_is_directory=True)
    run(project, FakeFetch({FEED_URL: GOOD_FEED}))
    assert not (project.out / "link.txt").exists() and not (project.out / "linked-dir").exists()
    assert (project.out / "logic.js").exists()


# --- sources.json version 2: feeds per source, one fetch per distinct URL (F3: R14, R15.1) -----

OTHER_URL = "https://news.example.invalid/all/rss.xml"
ALL_TOPICS = ["all-news", "politics", "nature", "ai"]
HOST = "https://news.example.invalid"


def svt_shaped(**changes):
    """A build source shaped like SVT in design 7.5: all-news, nature and ai share one address,
    politics has its own."""
    feeds = [{"topic": "all-news", "method": "feed", "url": OTHER_URL},
             {"topic": "politics", "method": "keywordFilter", "url": FEED_URL},
             {"topic": "nature", "method": "keywordFilter", "url": OTHER_URL},
             {"topic": "ai", "method": "keywordFilter", "url": OTHER_URL}]
    return source(feeds=feeds, **changes)


def feed_requests(fetch):
    """The feed requests of a fake fetch layer: everything except robots.txt (R15.1)."""
    return [c for c in fetch.calls if not c.endswith("/robots.txt")]


def stamp(hour, minute=0):
    return "Fri, 13 Nov 2026 %02d:%02d:00 GMT" % (hour, minute)


def by_url(document):
    return {i["url"][len(HOST):]: i for i in document["items"]}


def feed_of(document, topic, source_id="test-news"):
    return next(f for f in source_entry(document, source_id)["feeds"] if f["topic"] == topic)


# Invented feeds for the SVT-shaped source: OTHER_URL is the broad feed, FEED_URL the domestic one.
BROAD = rss(
    ("Regeringen testar ChatGPT i ett naturreservat", "/b/1", stamp(11)),   # all-news, nature, ai (broad feed)
    ("Naturreservat vid sjön får nya stigar", "/b/2", stamp(10)),           # all-news, nature
    ("ChatGPT i skolan", "/b/3", stamp(9)),                                 # all-news, ai
    ("Vädret blir fint i helgen", "/b/4", stamp(8)),                        # all-news
    ("Riksdagen debatterar i den broad-feeden", "/b/5", stamp(7)),          # all-news only: politics comes from the other feed
)
DOMESTIC = rss(
    ("Regeringen testar ChatGPT i ett naturreservat", "/b/1", stamp(11)),   # the same article: politics is joined
    ("Riksdagen debatterar exempelfrågan", "/d/1", stamp(10, 30)),          # politics
    ("Vädret är en inrikesfråga", "/d/2", stamp(9, 30)),                    # no keyword: in no topic
)


def full_fetch(**changes):
    responses = {ROBOTS_URL: ROBOTS_OK, OTHER_URL: BROAD, FEED_URL: DOMESTIC}
    responses.update(changes)
    return FakeFetch(responses)


def test_distinct_feed_urls_are_collected_once_each_in_order(project):
    assert build_module.distinct_feed_urls(svt_shaped(), ("all-news", "politics", "nature", "ai")) == [OTHER_URL, FEED_URL]
    assert build_module.distinct_feed_urls(svt_shaped()) == [OTHER_URL, FEED_URL]  # BUILD_TOPICS: all four
    assert build_module.distinct_feed_urls(svt_shaped(), ("nature", "ai")) == [OTHER_URL]
    assert build_module.distinct_feed_urls(svt_shaped(), ("politics",)) == [FEED_URL]
    assert build_module.distinct_feed_urls(svt_shaped(), ()) == []
    assert build_module.BUILD_TOPICS == ("all-news", "politics", "nature", "ai")


def test_all_topics_cost_one_request_per_distinct_url(project):
    # R15.1: the address that three topics share is requested once, the other once,
    # robots.txt once per host (not counted).
    project.write_sources(svt_shaped())
    fetch = full_fetch()
    document = run(project, fetch)
    assert sorted(feed_requests(fetch)) == sorted([FEED_URL, OTHER_URL])
    assert fetch.calls.count(ROBOTS_URL) == 1
    assert source_entry(document)["status"] == "ok"


def test_all_topics_one_address_for_every_entry_is_one_request(project):
    feeds = [{"topic": t, "method": "feed" if t == "all-news" else "keywordFilter", "url": FEED_URL}
             for t in ALL_TOPICS]
    project.write_sources(source(feeds=feeds))
    fetch = FakeFetch({ROBOTS_URL: ROBOTS_OK, FEED_URL: GOOD_FEED})
    run(project, fetch)
    assert feed_requests(fetch) == [FEED_URL]


def test_items_get_their_topics_and_an_article_in_two_feeds_is_one_item_with_joined_topics(project):
    project.write_sources(svt_shaped())
    document = run(project, full_fetch())
    items = by_url(document)
    assert len(document["items"]) == len({i["url"] for i in document["items"]}) == 6
    assert items["/b/1"]["topics"] == ["all-news", "politics", "nature", "ai"]  # R13.5: union, order of R13.1
    assert items["/b/2"]["topics"] == ["all-news", "nature"]
    assert items["/b/3"]["topics"] == ["all-news", "ai"]
    assert items["/b/4"]["topics"] == ["all-news"]
    assert items["/b/5"]["topics"] == ["all-news"]  # "Riksdagen" in the broad feed: the politics rule is on the other feed (R13.3)
    assert items["/d/1"]["topics"] == ["politics"]
    assert "/d/2" not in items  # no topic: dropped (R13.3)
    assert all(set(i) == ITEM_FIELDS for i in document["items"])
    assert [i["published"] for i in document["items"]] == sorted((i["published"] for i in document["items"]), reverse=True)


def test_status_per_source_and_feed_when_everything_works(project):
    project.write_sources(svt_shaped())
    document = run(project, full_fetch())
    entry = source_entry(document)
    assert entry["status"] == "ok" and entry["lastSuccess"] == "2026-11-13T12:00:00Z"
    assert entry["itemCount"] == 6 and "message" not in entry
    assert entry["feeds"] == [
        {"topic": t, "status": "ok", "lastSuccess": "2026-11-13T12:00:00Z", "itemCount": n}
        for t, n in (("all-news", 5), ("politics", 2), ("nature", 2), ("ai", 2))]
    text = (project.out / "news.json").read_text(encoding="utf-8")
    assert "news.example.invalid/all/rss.xml" not in text  # no feed address in news.json (R19.3)


def test_the_cap_is_per_source_and_topic_and_an_item_keeps_only_the_topics_it_was_kept_in(project):
    feeds = [{"topic": "all-news", "method": "feed", "url": OTHER_URL},
             {"topic": "politics", "method": "keywordFilter", "url": OTHER_URL}]
    project.write_sources(source(feeds=feeds))
    plain = [("Vanlig nyhet %d" % n, "/p/%d" % n, stamp(11, 59 - n)) for n in range(24)]
    old_politics = ("Riksdagen om en gammal fråga", "/p/old", stamp(1))      # oldest of 25: not in the 20 newest
    document = run(project, FakeFetch({ROBOTS_URL: ROBOTS_OK, OTHER_URL: rss(*plain, old_politics)}))
    items = by_url(document)
    assert len(document["items"]) == 21  # the 21st plain item has no topic left and is dropped
    assert sum("all-news" in i["topics"] for i in document["items"]) == 20
    assert items["/p/old"]["topics"] == ["politics"]  # cut from all-news, kept in politics (R13.6)
    assert "/p/23" not in items and "/p/19" in items
    feeds_out = {f["topic"]: f["itemCount"] for f in source_entry(document)["feeds"]}
    assert feeds_out == {"all-news": 20, "politics": 1}
    assert source_entry(document)["itemCount"] == 21


def test_an_item_older_than_seven_days_is_dropped_in_every_topic(project):
    old = rss(("Riksdagen i en gammal fråga", "/o/1", "Thu, 05 Nov 2026 11:00:00 GMT"),
              ("Riksdagen i en ny fråga", "/o/2", stamp(11)))
    project.write_sources(svt_shaped())
    document = run(project, full_fetch(**{OTHER_URL: old, FEED_URL: old}))
    assert [i["url"][len(HOST):] for i in document["items"]] == ["/o/2"]


# --- one failing feed (R15.2, R19.3, R19.4) ---------------------------------

def previous_v2(path, feed_success, items, source_success=None):
    """A previous news.json of version 2 for the SVT-shaped source. `feed_success`: topic -> lastSuccess."""
    document = {
        "version": 2, "generatedAt": "2026-11-13T10:00:00Z", "generatedAtDisplay": "x", "topics": ALL_TOPICS,
        "sources": [{"id": "test-news", "name": "Test News", "status": "ok",
                     "lastSuccess": source_success or min(feed_success.values()), "itemCount": len(items),
                     "feeds": [{"topic": t, "status": "ok", "lastSuccess": feed_success[t], "itemCount": 0}
                               for t in ALL_TOPICS if t in feed_success]}],
        "items": [{"id": "0123456789abcdef", "sourceId": "test-news", "sourceName": "Test News",
                   "title": title, "url": HOST + path, "published": "2026-11-13T09:00:00Z",
                   "publishedDisplay": "2026-11-13 10:00", "topics": topics} for title, path, topics in items]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def hours_ago(hours, minutes=0):
    return (NOW - timedelta(hours=hours, minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_one_failing_feed_does_not_hide_the_others_and_does_not_stop_further_requests(project):
    # The F3 rule "stop after the first failing address" is gone: a failure is per URL (R15.2).
    project.write_sources(svt_shaped())
    fetch = full_fetch(**{OTHER_URL: FetchError("timeout", "timeout")})
    document = run(project, fetch)
    assert feed_requests(fetch) == [OTHER_URL, FEED_URL]
    entry = source_entry(document)
    assert entry["status"] == "error" and entry["message"] == "fetch failed: timeout"
    statuses = {f["topic"]: f["status"] for f in entry["feeds"]}
    assert statuses == {"all-news": "error", "politics": "ok", "nature": "error", "ai": "error"}
    assert "message" not in feed_of(document, "politics")
    assert feed_of(document, "nature")["message"] == "fetch failed: timeout"  # the three entries share it
    assert [i["url"][len(HOST):] for i in document["items"]] == ["/b/1", "/d/1"]  # the politics feed is current
    assert entry["lastSuccess"] is None  # three feeds have never succeeded


def test_the_fallback_is_per_feed_and_keeps_only_the_topics_of_the_failed_feed(project):
    project.write_sources(svt_shaped())
    previous_v2(project.out / "news.json",
                {"all-news": hours_ago(2), "politics": hours_ago(1), "nature": hours_ago(2), "ai": hours_ago(2)},
                [("Gammal nyhet om allt", "/old/1", ["all-news", "politics"]),
                 ("Gammal naturnyhet", "/old/2", ["all-news", "nature"]),
                 ("Bara politik förut", "/old/3", ["politics"])])
    fetch = full_fetch(**{OTHER_URL: FetchError("timeout", "timeout")})
    document = run(project, fetch)
    items = by_url(document)
    # The failed feed entries are all-news, nature and ai: only those topics come back from the old file.
    assert items["/old/1"]["topics"] == ["all-news"]
    assert items["/old/2"]["topics"] == ["all-news", "nature"]
    assert "/old/3" not in items  # politics is current (its feed worked), so its old items are not added
    assert items["/d/1"]["topics"] == ["politics"] and items["/b/1"]["topics"] == ["politics"]
    entry = source_entry(document)
    assert entry["status"] == "error"
    assert entry["lastSuccess"] == hours_ago(2)  # the oldest lastSuccess of the feeds
    assert feed_of(document, "all-news") == {"topic": "all-news", "status": "error", "lastSuccess": hours_ago(2),
                                             "itemCount": 2, "message": "fetch failed: timeout"}
    assert feed_of(document, "politics")["lastSuccess"] == "2026-11-13T12:00:00Z"


def test_a_fresh_item_and_its_old_copy_are_one_item_with_the_fresh_text_and_joined_topics(project):
    project.write_sources(svt_shaped())
    previous_v2(project.out / "news.json",
                {"all-news": hours_ago(1), "politics": hours_ago(1), "nature": hours_ago(1), "ai": hours_ago(1)},
                [("Gammal rubrik", "/d/1", ["all-news", "nature"])])
    document = run(project, full_fetch(**{OTHER_URL: FetchError("timeout", "timeout")}))
    item = by_url(document)["/d/1"]
    assert item["title"] == "Riksdagen debatterar exempelfrågan"
    assert item["topics"] == ["all-news", "politics", "nature"]


def test_the_fallback_is_refused_per_feed_after_24_hours(project):
    project.write_sources(svt_shaped())
    previous_v2(project.out / "news.json",
                {"all-news": hours_ago(24), "politics": hours_ago(1), "nature": hours_ago(23, 59), "ai": hours_ago(30)},
                [("Gammal nyhet", "/old/1", ["all-news", "nature", "ai"])])
    document = run(project, full_fetch(**{OTHER_URL: FetchError("timeout", "timeout")}))
    old = by_url(document)["/old/1"]
    assert old["topics"] == ["nature"]  # only the feed that failed less than 24 hours after its success
    assert feed_of(document, "all-news")["lastSuccess"] == hours_ago(24)  # the last real success is kept
    assert feed_of(document, "ai")["itemCount"] == 0 and feed_of(document, "nature")["itemCount"] == 1


def test_the_cap_is_applied_again_after_previous_items_are_added(project):
    feeds = [{"topic": "all-news", "method": "feed", "url": OTHER_URL},
             {"topic": "nature", "method": "keywordFilter", "url": FEED_URL}]
    project.write_sources(source(feeds=feeds))
    previous_v2(project.out / "news.json", {"all-news": hours_ago(1), "nature": hours_ago(1)},
                [("Gammal nyhet %d" % n, "/old/%d" % n, ["all-news"]) for n in range(25)])
    nature = rss(("Naturreservat vid sjön", "/n/1", stamp(8)), ("Naturreservat vid havet", "/n/2", stamp(7)))
    document = run(project, FakeFetch({ROBOTS_URL: ROBOTS_OK, OTHER_URL: FetchError("timeout", "timeout"),
                                       FEED_URL: nature}))
    assert feed_of(document, "all-news")["itemCount"] == 20  # 25 old items, 20 kept
    assert feed_of(document, "nature")["itemCount"] == 2
    assert len(document["items"]) == 22
    # The old items have the time 09:00, newer than the nature items; the 20 newest per topic are kept.
    assert {"/n/1", "/n/2"} <= set(by_url(document))


def test_a_version_1_previous_file_gives_politics_to_the_politics_feed_only(project):
    project.write_sources(svt_shaped())
    last = hours_ago(1)
    previous_file(project.out / "news.json", last)  # version 1: one item, one source lastSuccess
    document = run(project, full_fetch(**{FEED_URL: FetchError("timeout", "timeout"),
                                          OTHER_URL: FetchError("timeout", "timeout")}))
    assert [i["title"] for i in document["items"]] == ["Gammal riksdagsrubrik"]
    assert document["items"][0]["topics"] == ["politics"]
    assert feed_of(document, "politics")["lastSuccess"] == last and feed_of(document, "politics")["itemCount"] == 1
    for topic in ("all-news", "nature", "ai"):
        assert feed_of(document, topic)["lastSuccess"] is None and feed_of(document, topic)["itemCount"] == 0
    assert source_entry(document)["lastSuccess"] is None  # some feed never succeeded


def test_a_version_1_previous_file_next_to_a_working_feed_is_not_added_to_it(project):
    project.write_sources(svt_shaped())
    previous_file(project.out / "news.json", hours_ago(1))
    document = run(project, full_fetch())
    assert "Gammal riksdagsrubrik" not in [i["title"] for i in document["items"]]


def test_previous_items_with_wrong_topics_or_fields_are_not_kept(project):
    project.write_sources(svt_shaped())
    previous_v2(project.out / "news.json", {t: hours_ago(1) for t in ALL_TOPICS},
                [("Bra", "/old/ok", ["all-news"]), ("Tom lista", "/old/1", []),
                 ("Okänt ämne", "/old/2", ["sport"]), ("Fel typ", "/old/3", "all-news")])
    document = run(project, full_fetch(**{OTHER_URL: FetchError("timeout", "timeout")}))
    assert "/old/ok" in by_url(document)
    assert not {"/old/1", "/old/2", "/old/3"} & set(by_url(document))
    # A version 1 item (seven fields) inside a version 2 file is not trusted either.
    path = project.out / "news.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["items"] = [{k: v for k, v in data["items"][0].items() if k != "topics"}]
    path.write_text(json.dumps(data), encoding="utf-8")
    document = run(project, full_fetch(**{OTHER_URL: FetchError("timeout", "timeout")}))
    assert "/old/ok" not in by_url(document)


def test_an_unknown_previous_version_is_ignored(project):
    project.write_sources(svt_shaped())
    previous_v2(project.out / "news.json", {t: hours_ago(1) for t in ALL_TOPICS}, [("Gammal", "/old/1", ["all-news"])])
    data = json.loads((project.out / "news.json").read_text(encoding="utf-8"))
    data["version"] = 3
    (project.out / "news.json").write_text(json.dumps(data), encoding="utf-8")
    document = run(project, full_fetch(**{OTHER_URL: FetchError("timeout", "timeout")}))
    assert "/old/1" not in by_url(document)


def test_a_blocked_address_marks_every_feed_entry_that_uses_it_and_keeps_nothing(project):
    project.write_sources(svt_shaped())
    previous_v2(project.out / "news.json", {t: hours_ago(1) for t in ALL_TOPICS}, [("Gammal", "/old/1", ["all-news"])])
    robots = b"User-agent: *\nDisallow: /all/\n"
    fetch = full_fetch(**{ROBOTS_URL: robots})
    document = run(project, fetch)
    assert feed_requests(fetch) == [FEED_URL]  # robots.txt read once; the blocked address is not requested
    assert fetch.calls.count(ROBOTS_URL) == 1
    statuses = {f["topic"]: f["status"] for f in source_entry(document)["feeds"]}
    assert statuses == {"all-news": "blocked-by-robots", "politics": "ok", "nature": "blocked-by-robots",
                        "ai": "blocked-by-robots"}
    entry = source_entry(document)
    assert entry["status"] == "blocked-by-robots" and entry["message"] == "robots.txt does not allow this address"
    assert "/old/1" not in by_url(document)  # a blocked feed keeps nothing (R6.6)
    assert [i["url"][len(HOST):] for i in document["items"]] == ["/b/1", "/d/1"]  # only what the politics feed gave


def test_the_worst_status_and_the_message_of_the_first_feed_with_it(project):
    # all-news fails (error), politics is blocked: the source is `error`, with the message of the
    # first feed that has that status.
    project.write_sources(svt_shaped())
    robots = b"User-agent: *\nDisallow: /politics/\n"
    fetch = full_fetch(**{ROBOTS_URL: robots, OTHER_URL: FetchError("status", "HTTP status 500", 500)})
    document = run(project, fetch)
    entry = source_entry(document)
    assert [f["status"] for f in entry["feeds"]] == ["error", "blocked-by-robots", "error", "error"]
    assert entry["status"] == "error" and entry["message"] == "fetch failed: HTTP status 500"
    assert feed_of(document, "politics")["message"] == "robots.txt does not allow this address"


def test_worst_status_when_the_first_feed_is_ok_and_a_later_one_is_not(project):
    # politics (second address) fails, all-news (first address) is ok: the source is not ok.
    project.write_sources(svt_shaped())
    previous_v2(project.out / "news.json", {t: hours_ago(3) for t in ALL_TOPICS}, [])
    fetch = full_fetch(**{FEED_URL: FetchError("timeout", "timeout")})
    document = run(project, fetch)
    entry = source_entry(document)
    assert [f["status"] for f in entry["feeds"]] == ["ok", "error", "ok", "ok"]
    assert entry["status"] == "error" and entry["message"] == "fetch failed: timeout"
    assert entry["lastSuccess"] == hours_ago(3)  # the oldest: the failed feed's previous success
    assert "message" not in feed_of(document, "all-news")


def test_a_later_blocked_feed_makes_the_source_blocked_and_the_oldest_success_wins(project):
    project.write_sources(svt_shaped())
    previous_v2(project.out / "news.json", {t: hours_ago(5) for t in ALL_TOPICS}, [])
    robots = b"User-agent: *\nDisallow: /politics/\n"
    document = run(project, full_fetch(**{ROBOTS_URL: robots}))
    entry = source_entry(document)
    assert [f["status"] for f in entry["feeds"]] == ["ok", "blocked-by-robots", "ok", "ok"]
    assert entry["status"] == "blocked-by-robots"
    assert entry["message"] == "robots.txt does not allow this address"
    assert entry["lastSuccess"] == hours_ago(5)


def test_the_message_is_the_first_one_of_the_worst_status_when_messages_differ(project):
    # Three more feed addresses: the first error message in sources.json order is the source's.
    urls = ["https://news.example.invalid/%s.xml" % n for n in ("a", "b", "c")]
    feeds = [{"topic": "all-news", "method": "feed", "url": urls[0]},
             {"topic": "politics", "method": "keywordFilter", "url": urls[1]},
             {"topic": "nature", "method": "keywordFilter", "url": urls[2]},
             {"topic": "ai", "method": "keywordFilter", "url": FEED_URL}]
    project.write_sources(source(feeds=feeds))
    fetch = FakeFetch({ROBOTS_URL: ROBOTS_OK, urls[0]: GOOD_FEED, urls[1]: FetchError("timeout", "timeout"),
                       urls[2]: FetchError("status", "HTTP status 500", 500), FEED_URL: GOOD_FEED})
    document = run(project, fetch)
    entry = source_entry(document)
    assert entry["status"] == "error" and entry["message"] == "fetch failed: timeout"
    assert feed_of(document, "nature")["message"] == "fetch failed: HTTP status 500"


def test_an_unrelated_value_error_in_selection_is_a_failed_feed_not_a_crash(project, monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("unrelated")
    monkeypatch.setattr(build_module, "topics_of", boom)
    project.write_sources(svt_shaped())
    document = run(project, full_fetch())
    entry = source_entry(document)
    assert entry["status"] == "error" and entry["message"] == "selection failed (ValueError)"
    assert "unrelated" not in json.dumps(document)
    assert [f["status"] for f in entry["feeds"]] == ["error"] * 4


def test_a_previous_success_in_the_future_gives_no_fallback(project):
    project.write_sources(svt_shaped())
    future = (NOW + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    previous_v2(project.out / "news.json", {t: future for t in ALL_TOPICS}, [("Gammal", "/old/1", ["all-news"])])
    document = run(project, full_fetch(**{OTHER_URL: FetchError("timeout", "timeout")}))
    assert "/old/1" not in by_url(document)
    assert feed_of(document, "all-news")["status"] == "error"


def test_a_fresh_second_copy_of_an_article_whose_first_copy_is_too_old_gives_the_item(project):
    project.write_sources(svt_shaped())
    old = rss(("Riksdagen och ChatGPT, gammal kopia", "/o/1", "Thu, 05 Nov 2026 11:00:00 GMT"))
    fresh = rss(("Riksdagen debatterar, färsk kopia", "/o/1", stamp(11)))
    document = run(project, full_fetch(**{OTHER_URL: old, FEED_URL: fresh}))
    assert [(i["title"], i["topics"]) for i in document["items"]] == [
        ("Riksdagen debatterar, färsk kopia", ["politics"])]  # nothing from the old copy, not even its topics


def test_a_version_3_previous_file_with_version_1_items_is_ignored(project):
    project.write_sources(svt_shaped())
    previous_file(project.out / "news.json", hours_ago(1))
    path = project.out / "news.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = 3
    path.write_text(json.dumps(data), encoding="utf-8")
    document = run(project, full_fetch(**{FEED_URL: FetchError("timeout", "timeout"),
                                          OTHER_URL: FetchError("timeout", "timeout")}))
    assert document["items"] == []


def test_unreadable_robots_marks_every_feed_of_the_host_as_error(project):
    project.write_sources(svt_shaped())
    fetch = full_fetch(**{ROBOTS_URL: FetchError("timeout", "timeout")})
    document = run(project, fetch)
    assert feed_requests(fetch) == []
    assert [f["status"] for f in source_entry(document)["feeds"]] == ["error"] * 4
    assert fetch.calls.count(ROBOTS_URL) == 1


def test_a_category_filter_feed_fails_only_its_own_address(project):
    feeds = [{"topic": "all-news", "method": "feed", "url": OTHER_URL},
             {"topic": "politics", "method": "categoryFilter", "url": FEED_URL}]
    project.write_sources(source(feeds=feeds))
    document = run(project, full_fetch())
    assert feed_of(document, "all-news")["status"] == "ok" and feed_of(document, "all-news")["itemCount"] == 5
    politics_feed = feed_of(document, "politics")
    assert politics_feed["status"] == "error" and "categoryFilter" in politics_feed["message"]
    assert "ValueError" in politics_feed["message"] and "selection failed" in politics_feed["message"]


def test_a_source_that_offers_one_topic_only_requests_only_its_address(project):
    # R13.7: a topic without a feed entry is not an error and not a request.
    project.write_sources(source(feeds=[{"topic": "nature", "method": "keywordFilter", "url": FEED_URL}]))
    fetch = FakeFetch({ROBOTS_URL: ROBOTS_OK, FEED_URL: rss(("Naturreservat vid sjön", "/n/1", stamp(9)),
                                                           ("Riksdagen debatterar", "/n/2", stamp(8)))})
    document = run(project, fetch)
    assert feed_requests(fetch) == [FEED_URL]
    assert [(i["url"][len(HOST):], i["topics"]) for i in document["items"]] == [("/n/1", ["nature"])]
    assert [f["topic"] for f in source_entry(document)["feeds"]] == ["nature"]


def test_the_same_article_twice_in_one_feed_keeps_the_first_and_joins_topics(project):
    feeds = [{"topic": "all-news", "method": "feed", "url": FEED_URL},
             {"topic": "ai", "method": "keywordFilter", "url": FEED_URL}]
    project.write_sources(source(feeds=feeds))
    twice = rss(("Första rubriken", "/t/1", stamp(9)), ("ChatGPT i andra rubriken", "/t/1?utm=x", stamp(8)))
    document = run(project, FakeFetch({ROBOTS_URL: ROBOTS_OK, FEED_URL: twice}))
    assert [(i["title"], i["topics"]) for i in document["items"]] == [("Första rubriken", ["all-news", "ai"])]


def test_news_json_of_the_real_sources_has_the_svt_items_with_topics_and_two_feed_requests(tmp_path):
    svt_all = "https://www.svt.se/nyheter/rss.xml"
    svt_domestic = "https://www.svt.se/nyheter/inrikes/rss.xml"

    def feed(*items):
        return rss(*items).replace(b"news.example.invalid", b"www.svt.se")

    fetch = FakeFetch({
        "https://www.svt.se/robots.txt": ROBOTS_OK,
        svt_all: feed(("Naturreservat vid sjön får nya stigar", "/nyheter/a", stamp(11)),
                      ("Regeringen testar ChatGPT", "/nyheter/inrikes/b", stamp(10))),
        svt_domestic: feed(("Regeringen testar ChatGPT", "/nyheter/inrikes/b", stamp(10)))})
    document = build(tmp_path / "real", NOW, fetch)
    assert fetch.calls == ["https://www.svt.se/robots.txt", svt_all, svt_domestic]  # two feed requests (R15.1)
    items = {i["url"]: i for i in document["items"]}
    assert items["https://www.svt.se/nyheter/a"]["topics"] == ["all-news", "nature"]
    assert items["https://www.svt.se/nyheter/inrikes/b"]["topics"] == ["all-news", "politics", "ai"]
    assert [f["topic"] for f in source_entry(document, "svt")["feeds"]] == ALL_TOPICS
    assert document["topics"] == ALL_TOPICS


def test_the_output_guard_refuses_a_document_that_breaks_the_shape(project):
    good_item = {"id": "a", "sourceId": "test-news", "sourceName": "T", "title": "t", "url": "u",
                 "published": None, "publishedDisplay": "Tid saknas", "topics": ["politics"]}
    good_feed = {"topic": "politics", "status": "ok", "lastSuccess": None, "itemCount": 1}
    good = {"version": 2, "topics": ALL_TOPICS, "items": [good_item],
            "sources": [{"id": "test-news", "status": "ok", "feeds": [good_feed]}]}
    build_module._check_document(good, [source()], ALL_TOPICS)  # no error
    bad_items = [dict(good_item, topics=[]), dict(good_item, topics=["ai", "politics"]),
                 dict(good_item, topics=["politics", "politics"]), dict(good_item, topics=["sport"]),
                 {k: v for k, v in good_item.items() if k != "topics"}]
    for item in bad_items:
        with pytest.raises(BuildError, match="internal error"):
            build_module._check_document(dict(good, items=[item]), [source()], ALL_TOPICS)
    for change in ({"version": 1}, {"topics": ["politics"]},
                   {"sources": [{"id": "test-news", "status": "error", "feeds": [good_feed]}]},  # no message
                   {"sources": [{"id": "test-news", "status": "ok", "feeds": [dict(good_feed, topic="sport")]}]}):
        with pytest.raises(BuildError, match="internal error"):
            build_module._check_document(dict(good, **change), [source()], ALL_TOPICS)


def test_cli_prints_the_status_of_each_feed(project, capsys):
    project.write_sources(svt_shaped())
    fetch = full_fetch(**{OTHER_URL: FetchError("timeout", "timeout")})
    assert main(["--out", str(project.out)], fetch=fetch, now=NOW, root=project.root) == 0
    out = capsys.readouterr().out
    assert "test-news: error, 2 items (fetch failed: timeout)" in out
    assert "  politics: ok, 2 items" in out
    assert "  nature: error, 0 items (fetch failed: timeout)" in out


def test_a_version_1_sources_file_fails_the_build_and_writes_nothing(project):
    (project.root / "sources.json").write_text(json.dumps({"version": 1, "sources": [
        dict({k: v for k, v in source().items() if k != "feeds"},
             **{"politics-sweden": {"method": "keywordFilter", "url": FEED_URL}})]}), encoding="utf-8")
    with pytest.raises(BuildError, match="^sources.json version 1 is no longer supported$"):
        run(project, FakeFetch())
    assert not project.out.exists()


def test_the_copied_sources_json_is_version_2(project):
    run(project, FakeFetch({ROBOTS_URL: ROBOTS_OK, FEED_URL: GOOD_FEED}))
    assert json.loads((project.out / "sources.json").read_text("utf-8"))["version"] == 2


# ---- --ca-file and certificate errors ------------------------------------------

def _ca_file(tmp_path, text=None):
    from tests.test_fetch import TEST_CERTIFICATE_PEM
    path = tmp_path / "extra.pem"
    path.write_text(TEST_CERTIFICATE_PEM if text is None else text, encoding="ascii")
    return path


def _der_file(tmp_path):
    import base64
    from tests.test_fetch import TEST_CERTIFICATE_PEM
    body = "".join(l for l in TEST_CERTIFICATE_PEM.splitlines() if "-----" not in l)
    path = tmp_path / "extra.der"
    path.write_bytes(base64.b64decode(body))
    return path


def test_cli_ca_file_is_accepted_and_the_context_is_passed_on(project, tmp_path, monkeypatch):
    import ssl
    seen = []

    def fake_make_fetch(context=None):
        seen.append(context)
        return FakeFetch({ROBOTS_URL: ROBOTS_OK, FEED_URL: GOOD_FEED})

    monkeypatch.setattr(fetch_module, "make_fetch", fake_make_fetch)
    code = main(["--out", str(project.out), "--ca-file", str(_ca_file(tmp_path))], now=NOW, root=project.root)
    assert code == 0 and len(seen) == 1
    assert seen[0].verify_mode == ssl.CERT_REQUIRED and seen[0].check_hostname is True
    assert read_news(project)["sources"][0]["itemCount"] == 2


def test_cli_without_ca_file_uses_the_plain_fetch(project, monkeypatch):
    monkeypatch.setattr(fetch_module, "make_fetch", lambda context=None: pytest.fail("no context expected"))
    monkeypatch.setattr(fetch_module, "fetch_url", FakeFetch({ROBOTS_URL: ROBOTS_OK, FEED_URL: GOOD_FEED}))
    assert main(["--out", str(project.out)], now=NOW, root=project.root) == 0


@pytest.mark.parametrize("kind", ["missing", "directory", "text", "der"])
def test_cli_bad_ca_file_fails_early_and_writes_nothing(project, tmp_path, capsys, kind):
    path = {"missing": tmp_path / "nope.pem", "directory": tmp_path,
            "text": _ca_file(tmp_path, "just some text\n"), "der": _der_file(tmp_path)}[kind]
    fetch = FakeFetch({ROBOTS_URL: ROBOTS_OK, FEED_URL: GOOD_FEED})
    with pytest.raises(SystemExit) as info:
        main(["--out", str(project.out), "--ca-file", str(path)], fetch=fetch, now=NOW, root=project.root)
    assert info.value.code == 2
    err = capsys.readouterr().err
    expected = {"missing": "the file does not exist or cannot be read",
                "directory": "the file does not exist or cannot be read",
                "text": "the file has no usable certificate (it must be a PEM file, Base-64 text)",
                "der": "the file has no usable certificate (it must be a PEM file, Base-64 text)"}[kind]
    assert err.strip().splitlines()[-1] == "python -m newsreader: error: --ca-file: " + expected
    assert str(tmp_path) not in err
    assert fetch.calls == [] and not project.out.exists()


def test_certificate_failure_shows_the_message_for_riksdagen_and_svt_stays_ok(project, capsys):
    from tests.test_riksdagen import FEED_URL as RD_FEED, ROBOTS as RD_ROBOTS, real_riksdagen
    project.write_sources(source(), real_riksdagen())
    fetch = FakeFetch({ROBOTS_URL: ROBOTS_OK, FEED_URL: GOOD_FEED,
                       RD_ROBOTS: FetchError("certificate", fetch_module.CERTIFICATE_MESSAGE)})
    assert main(["--out", str(project.out)], fetch=fetch, now=NOW, root=project.root) == 0
    document = read_news(project)
    assert source_entry(document, "test-news")["status"] == "ok"
    entry = source_entry(document, "riksdagen")
    assert entry["status"] == "error" and "certificate could not be verified" in entry["message"]
    assert "README" in entry["message"] and "http" not in entry["message"]
    for feed in entry["feeds"]:
        assert feed["status"] == "error" and "http" not in feed["message"]
    out = capsys.readouterr().out
    assert "test-news: ok" in out and "certificate could not be verified" in out
