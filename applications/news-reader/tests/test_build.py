"""The build command with a fake fetch layer: no network, invented feeds and hosts."""
import json
import runpy
import sys
from datetime import timedelta

import pytest

from newsreader import build as build_module
from newsreader import fetch as fetch_module
from newsreader.__main__ import main
from newsreader.build import BuildError, build
from newsreader.fetch import FetchError
from newsreader.parse import MAX_RESPONSE_BYTES
from tests.fakes import (BROWSER_FEED_URL, FEED_URL, GOOD_FEED, NOW, ROBOTS_URL, FakeFetch,
                            APP, browser_source, rss, source)

ITEM_FIELDS = {"id", "sourceId", "sourceName", "title", "url", "published", "publishedDisplay"}
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
    assert document["version"] == 1
    assert document["category"] == "politics-sweden"
    assert document["generatedAt"] == "2026-11-13T12:00:00Z"
    assert document["generatedAtDisplay"] == "2026-11-13 13:00"
    assert document["sources"] == [{"id": "test-news", "name": "Test News", "status": "ok",
                                    "lastSuccess": "2026-11-13T12:00:00Z", "itemCount": 2}]
    titles = [i["title"] for i in document["items"]]
    assert titles == ["Riksdagen debatterar exempelfrågan", "Regeringen presenterar ett påhittat förslag"]
    first = document["items"][0]
    assert set(first) == ITEM_FIELDS
    assert first["sourceId"] == "test-news" and first["sourceName"] == "Test News"
    assert first["published"] == "2026-11-13T11:00:00Z"
    assert first["publishedDisplay"] == "2026-11-13 12:00"
    assert first["url"] == "https://news.example.invalid/a/1"


def test_news_json_is_utf8_with_swedish_letters(project):
    run(project, FakeFetch({FEED_URL: GOOD_FEED}))
    text = (project.out / "news.json").read_bytes().decode("utf-8")
    assert "påhittat" in text and "\\u00e5" not in text


def test_one_request_per_feed_and_one_robots_read(project):
    fetch = FakeFetch({ROBOTS_URL: ROBOTS_OK, FEED_URL: GOOD_FEED})
    project.write_sources(source(), source(id="second", name="Second",
                                           **{"politics-sweden": {"method": "keywordFilter",
                                                                  "url": "https://news.example.invalid/other.xml"}}))
    fetch.responses["https://news.example.invalid/other.xml"] = GOOD_FEED
    run(project, fetch)
    assert fetch.calls.count(ROBOTS_URL) == 1
    assert fetch.calls.count(FEED_URL) == 1
    assert fetch.calls.count("https://news.example.invalid/other.xml") == 1


def test_output_folder_has_the_copied_files(project):
    run(project, FakeFetch({FEED_URL: GOOD_FEED}))
    out = project.out
    assert (out / "logic.js").read_bytes() == (project.root / "site" / "logic.js").read_bytes()
    assert (out / "tests" / "logic.test.mjs").exists()  # the whole site folder is copied
    for name in ("sources.json", "politics-keywords.json"):
        assert (out / name).read_bytes() == (project.root / name).read_bytes()
    assert (out / "news.json").exists()


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
    FetchError("status", "HTTP status 500"),
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
    project.write_sources(source(**{"politics-sweden": {"method": "categoryFilter", "url": FEED_URL}}))
    document = run(project, FakeFetch({FEED_URL: GOOD_FEED}))
    entry = source_entry(document)
    assert entry["status"] == "error"
    assert "categoryFilter" in entry["message"] and "selection failed" in entry["message"]
    assert document["items"] == []


def test_one_failing_source_does_not_stop_the_other(project):
    other = "https://news.example.invalid/other.xml"
    project.write_sources(source(), source(id="second", name="Second",
                                           **{"politics-sweden": {"method": "keywordFilter", "url": other}}))
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


@pytest.mark.parametrize("robots", [
    FetchError("status", "HTTP status 404"),
    FetchError("timeout", "timeout"),
    RuntimeError("boom"),
    b"\xff\xfe garbage",
])
def test_missing_or_unreadable_robots_means_allowed(project, robots):
    document = run(project, FakeFetch({ROBOTS_URL: robots, FEED_URL: GOOD_FEED}))
    assert source_entry(document)["status"] == "ok"


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
    fetch = FakeFetch({"https://www.svt.se/robots.txt": ROBOTS_OK,
                       "https://www.svt.se/nyheter/inrikes/rss.xml": rss(
                           ("Riksdagen röstar om ett påhittat ärende", "/x", "Fri, 13 Nov 2026 11:00:00 GMT")
                       ).replace(b"news.example.invalid", b"www.svt.se"),
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
    document = {"sources": [{"id": "test-news"}],
                "items": [{"sourceId": "live-radio", "title": "Riksdagen (påhittad)"}]}
    with pytest.raises(BuildError, match="refusing"):
        build_module._check_document(document, [source(), browser_source()])
    document = {"sources": [{"id": "live-radio"}], "items": []}
    with pytest.raises(BuildError, match="refusing"):
        build_module._check_document(document, [source(), browser_source()])


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
    {"politics-sweden": {"method": "magic", "url": FEED_URL}},
    {"politics-sweden": {"method": "keywordFilter", "url": "http://news.example.invalid/x"}},
    {"politics-sweden": {"method": "keywordFilter", "url": "https://other.example.org/x"}},
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
    with pytest.raises(BuildError, match="politics-keywords.json"):
        run(project, FakeFetch())


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
    svt_feed = rss(("Regeringen och riksdagen i en påhittad fråga", "/nyheter/inrikes/exempel",
                    "Fri, 13 Nov 2026 11:00:00 GMT")).replace(b"news.example.invalid", b"www.svt.se")
    fake = FakeFetch({"https://www.svt.se/nyheter/inrikes/rss.xml": svt_feed})
    monkeypatch.setattr(fetch_module, "fetch_url", fake)
    out = tmp_path / "build"
    monkeypatch.setattr(sys, "argv", ["newsreader", "--out", str(out)])
    monkeypatch.delitem(sys.modules, "newsreader.__main__", raising=False)
    with pytest.raises(SystemExit) as info:
        runpy.run_module("newsreader", run_name="__main__")
    assert info.value.code == 0
    document = json.loads((out / "news.json").read_text(encoding="utf-8"))
    assert [s["id"] for s in document["sources"]] == ["svt"]
    assert fake.calls == ["https://www.svt.se/robots.txt", "https://www.svt.se/nyheter/inrikes/rss.xml"]
    assert (out / "sources.json").read_bytes() == (APP / "sources.json").read_bytes()
    assert (out / "politics-keywords.json").exists() and (out / "logic.js").exists()
