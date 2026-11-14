"""Validates sources.json (version 2) against the rules in news-reader-design.md (R3, R4, R13, R14, 7.5).

The real file is checked field by field, and `validate_sources` is checked with small
invalid copies. Only the NAMES of the keyword files are checked, not that the files exist (R14.1).
"""
import copy
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from newsreader.build import BuildError, distinct_feed_urls, validate_sources

ROOT = Path(__file__).resolve().parent.parent
METHODS = {"feed", "categoryFilter", "keywordFilter"}
FETCHED_BY = {"build", "browser"}
ID_ORDER = ["svt", "sveriges-radio"]
TOPIC_IDS = ["all-news", "politics", "nature", "ai"]
SR_URL = "https://api.sr.se/api/rss/program/83"
SVT_ALL = "https://www.svt.se/nyheter/rss.xml"
SVT_INRIKES = "https://www.svt.se/nyheter/inrikes/rss.xml"


@pytest.fixture(scope="module")
def config():
    return json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sources(config):
    return config["sources"]


def feeds_of(sources, sid):
    return {f["topic"]: f for f in next(s for s in sources if s["id"] == sid)["feeds"]}


# ---- the real file -------------------------------------------------------

def test_version(config):
    assert config["version"] == 2


def test_topics_are_the_four_topics_in_order(config):
    assert [t["id"] for t in config["topics"]] == TOPIC_IDS
    assert [t["label"] for t in config["topics"]] == ["Alla nyheter", "Politik", "Natur", "AI"]


def test_keyword_file_names_follow_the_name_rule(config):
    # R14.1: only the shape of the name; the files nature-keywords.json and ai-keywords.json
    # come with F4 and are checked from F5.
    for topic in config["topics"]:
        if topic["id"] == "all-news":
            assert "keywords" not in topic
        else:
            assert topic["keywords"] == topic["id"] + "-keywords.json"


def test_exactly_the_two_approved_sources(sources):
    assert [s["id"] for s in sources] == ID_ORDER
    assert [s["name"] for s in sources] == ["SVT", "Sveriges Radio"]


def test_riksdagen_is_not_added_yet(sources):
    assert all(s["id"] != "riksdagen" for s in sources)


def test_ids_are_unique(sources):
    ids = [s["id"] for s in sources]
    assert len(ids) == len(set(ids))


def test_required_fields_and_types(sources):
    for s in sources:
        assert isinstance(s["id"], str) and s["id"]
        assert isinstance(s["name"], str) and s["name"]
        assert isinstance(s["enabled"], bool)
        assert s["fetchedBy"] in FETCHED_BY
        assert isinstance(s["storageAllowed"], bool)
        assert urlparse(s["homepage"]).scheme == "https"
        assert isinstance(s["allowedHosts"], list) and s["allowedHosts"]
        assert all(isinstance(h, str) and h == h.lower() and "/" not in h
                   for h in s["allowedHosts"])
        assert "politics-sweden" not in s  # the version 1 key is gone (R14.2)


def test_each_feed_has_a_known_topic_a_method_and_an_https_url(sources):
    for s in sources:
        topics = [f["topic"] for f in s["feeds"]]
        assert topics and len(topics) == len(set(topics))  # at most one per topic (R14.3)
        for f in s["feeds"]:
            assert f["topic"] in TOPIC_IDS
            assert f["method"] in METHODS
            assert urlparse(f["url"]).scheme == "https"
            if f["topic"] == "all-news":
                assert f["method"] == "feed"


def test_urls_are_on_allowed_hosts_for_build_sources(sources):
    # The feed URL of a build source must be on its allowed hosts (R6.2, R14.3).
    for s in sources:
        if s["fetchedBy"] == "build":
            for f in s["feeds"]:
                host = urlparse(f["url"]).hostname
                assert any(host == h or host.endswith("." + h) for h in s["allowedHosts"])


def test_browser_source_is_never_stored(sources):
    # R3.2: a browser-fetched source must have storageAllowed false.
    for s in sources:
        if s["fetchedBy"] == "browser":
            assert s["storageAllowed"] is False


def test_sveriges_radio_is_browser_fetched_and_not_stored(sources):
    sr = next(s for s in sources if s["id"] == "sveriges-radio")
    assert sr["fetchedBy"] == "browser"
    assert sr["storageAllowed"] is False
    feeds = feeds_of(sources, "sveriges-radio")
    assert list(feeds) == TOPIC_IDS  # program 83 serves all four topics (D27)
    assert {f["url"] for f in feeds.values()} == {SR_URL}
    assert feeds["all-news"]["method"] == "feed"
    assert {feeds[t]["method"] for t in ("politics", "nature", "ai")} == {"keywordFilter"}


def test_svt_is_collected_by_the_build(sources):
    svt = next(s for s in sources if s["id"] == "svt")
    assert svt["fetchedBy"] == "build"
    assert svt["storageAllowed"] is True
    feeds = feeds_of(sources, "svt")
    assert list(feeds) == TOPIC_IDS
    assert feeds["all-news"]["url"] == SVT_ALL and feeds["all-news"]["method"] == "feed"
    assert feeds["politics"]["url"] == SVT_INRIKES and feeds["politics"]["method"] == "keywordFilter"
    for topic in ("nature", "ai"):
        assert feeds[topic]["url"] == SVT_ALL and feeds[topic]["method"] == "keywordFilter"


def test_the_real_file_is_valid_and_costs_two_svt_requests_and_one_sveriges_radio_request(config):
    validate_sources(config)
    by_id = {s["id"]: s for s in config["sources"]}
    all_topics = tuple(TOPIC_IDS)
    assert distinct_feed_urls(by_id["svt"], all_topics) == [SVT_ALL, SVT_INRIKES]
    assert distinct_feed_urls(by_id["sveriges-radio"], all_topics) == [SR_URL]
    # Until F5 the build evaluates politics only: one SVT address.
    assert distinct_feed_urls(by_id["svt"]) == [SVT_INRIKES]


def test_shared_cases_has_the_expected_sections():
    # Created empty in S2; later steps fill the sections (F4 adds `topics`), so only the shape is checked.
    cases = json.loads((ROOT / "tests" / "shared-cases.json").read_text(encoding="utf-8"))
    assert set(cases) == {"cleaning", "time", "keywords", "topics"}
    assert all(isinstance(v, list) for v in cases.values())


# ---- invalid copies (R14.1 to R14.3, R14.6) -------------------------------

def mutated(config, change):
    data = copy.deepcopy(config)
    change(data)
    return data


def svt(data):
    return data["sources"][0]


def sr(data):
    return data["sources"][1]


def swap(data, index, **fields):
    data["topics"][index] = {**data["topics"][index], **fields}


INVALID = {
    "version 2 as text": (lambda d: d.update(version="2"), "version must be 2"),
    "version 3": (lambda d: d.update(version=3), "version must be 2"),
    "no version": (lambda d: d.pop("version"), "version must be 2"),
    "no topics": (lambda d: d.pop("topics"), "topics"),
    "topics not a list": (lambda d: d.update(topics="x"), "topics"),
    "topic missing": (lambda d: d["topics"].pop(), "topics must be exactly"),
    "topics in the wrong order": (lambda d: d["topics"].reverse(), "topics must be exactly"),
    "unknown topic id": (lambda d: swap(d, 3, id="sport"), "topics must be exactly"),
    "topic without label": (lambda d: d["topics"][1].pop("label"), "label"),
    "politics without keywords": (lambda d: d["topics"][1].pop("keywords"), "keywords must be"),
    "keywords with a slash": (lambda d: swap(d, 1, keywords="a/politics-keywords.json"), "keywords must be"),
    "keywords with ..": (lambda d: swap(d, 1, keywords="../politics-keywords.json"), "keywords must be"),
    "keywords of the wrong form": (lambda d: swap(d, 1, keywords="politics.json"), "keywords must be"),
    "keywords of another topic": (lambda d: swap(d, 1, keywords="ai-keywords.json"), "keywords must be"),
    "keywords in capitals": (lambda d: swap(d, 2, keywords="Nature-keywords.json"), "keywords must be"),
    "keywords not text": (lambda d: swap(d, 2, keywords=7), "keywords must be"),
    "all-news with keywords": (lambda d: swap(d, 0, keywords="all-news-keywords.json"), "must not have keywords"),
    "no feeds": (lambda d: svt(d).pop("feeds"), "feeds must be a non-empty list"),
    "empty feeds": (lambda d: svt(d).update(feeds=[]), "feeds must be a non-empty list"),
    "old key politics-sweden only": (lambda d: (svt(d).pop("feeds"), svt(d).update(
        {"politics-sweden": {"method": "keywordFilter", "url": SVT_INRIKES}})), "feeds must be"),
    "feed not an object": (lambda d: svt(d)["feeds"].append("x"), "must be an object"),
    "unknown topic in a feed": (lambda d: svt(d)["feeds"][1].update(topic="sport"), "topic must be one of"),
    "two feeds for one topic": (lambda d: svt(d)["feeds"].append(dict(svt(d)["feeds"][2])), "second feed for the topic nature"),
    "unknown method": (lambda d: svt(d)["feeds"][1].update(method="magic"), "method must be one of"),
    "keywordFilter on all-news": (lambda d: svt(d)["feeds"][0].update(method="keywordFilter"), "all-news only uses"),
    "categoryFilter on all-news": (lambda d: svt(d)["feeds"][0].update(method="categoryFilter"), "all-news only uses"),
    "http feed": (lambda d: svt(d)["feeds"][1].update(url="http://www.svt.se/nyheter/inrikes/rss.xml"), "https address"),
    "feed without url": (lambda d: svt(d)["feeds"][1].pop("url"), "https address"),
    "feed url not text": (lambda d: svt(d)["feeds"][1].update(url=5), "https address"),
    "build feed on another host": (lambda d: svt(d)["feeds"][2].update(url="https://other.example.org/rss.xml"), "must be on allowedHosts"),
    "host that only ends alike": (lambda d: svt(d)["feeds"][2].update(url="https://notsvt.se/rss.xml"), "must be on allowedHosts"),
    "matchOn with feed": (lambda d: svt(d)["feeds"][0].update(matchOn="title"), "matchOn is allowed only"),
    "matchOn with another value": (lambda d: svt(d)["feeds"][1].update(matchOn="description"), "matchOn is allowed only"),
    "linkHosts not on allowedHosts": (lambda d: svt(d).update(linkHosts=["www.example.org"]), "linkHosts"),
    "linkHosts empty": (lambda d: svt(d).update(linkHosts=[]), "linkHosts"),
    "linkHosts in capitals": (lambda d: svt(d).update(linkHosts=["WWW.svt.se"]), "linkHosts"),
    "linkHosts with a path": (lambda d: svt(d).update(linkHosts=["www.svt.se/x"]), "linkHosts"),
    "empty credit": (lambda d: svt(d).update(credit=""), "credit"),
    "credit not text": (lambda d: svt(d).update(credit=["x"]), "credit"),
    "homepage not https": (lambda d: svt(d).update(homepage="http://www.svt.se/"), "homepage"),
    "browser source that may be stored": (lambda d: sr(d).update(storageAllowed=True), "storageAllowed false"),
    "build source that may not be stored": (lambda d: svt(d).update(storageAllowed=False), "storageAllowed true"),
    "duplicate source id": (lambda d: sr(d).update(id="svt"), "duplicate"),
}


@pytest.mark.parametrize("name", list(INVALID))
def test_invalid_copies_fail_with_a_message_that_names_the_field(config, name):
    change, text = INVALID[name]
    with pytest.raises(BuildError, match="sources.json") as error:
        validate_sources(mutated(config, change))
    assert text in str(error.value)


def test_error_messages_name_the_source_and_the_feed(config):
    data = mutated(config, lambda d: svt(d)["feeds"][1].update(method="magic"))
    with pytest.raises(BuildError) as error:
        validate_sources(data)
    assert "'svt'" in str(error.value) and "feeds[1]" in str(error.value)


def test_version_1_is_refused_with_the_documented_message(config):
    # R14.6: no code reads both versions.
    version_1 = {"version": 1, "sources": [{
        "id": "svt", "name": "SVT", "enabled": True, "fetchedBy": "build", "storageAllowed": True,
        "homepage": "https://www.svt.se/", "allowedHosts": ["svt.se"],
        "politics-sweden": {"method": "keywordFilter", "url": SVT_INRIKES}}]}
    with pytest.raises(BuildError) as error:
        validate_sources(version_1)
    assert str(error.value) == "sources.json version 1 is no longer supported"


@pytest.mark.parametrize("version", [2.0, True, "2", 3, None])
def test_only_the_integer_2_is_accepted_as_version(config, version):
    # type(version) is int: 2.0 and True are not versions (JSON "2.0" is a float in Python).
    with pytest.raises(BuildError, match="version must be 2"):
        validate_sources({**config, "version": version})


@pytest.mark.parametrize("url", [
    "https://www.svt.se:443/nyheter/rss.xml",
    "https://user@www.svt.se/nyheter/rss.xml",
    "https://www.svt.se\\nyheter/rss.xml",
    "https://www.svt.se/nyheter/rs s.xml",
    "https://www.svt.se/nyheter/rss.xml\n",
    " https://www.svt.se/nyheter/rss.xml",
    "https://www.svt.se/ny\theter/rss.xml",
    "https://www.svt.se./nyheter/rss.xml",
    "https://www.svt.se@evil.example.org/x",
    "https://www.svt.se/nyheter/\u00e5.xml",
    "https:///nyheter/rss.xml",
])
def test_feed_url_is_as_strict_as_the_link_check(config, url):
    with pytest.raises(BuildError, match="https address"):
        validate_sources(mutated(config, lambda d: svt(d)["feeds"][1].update(url=url)))


def test_optional_fields_credit_linkhosts_and_matchon_are_accepted(config):
    def add(d):
        s = svt(d)
        s["credit"] = "Källa: Exempel"
        s["linkHosts"] = ["www.svt.se"]
        s["feeds"][2]["matchOn"] = "title"
    assert validate_sources(mutated(config, add))


def test_a_source_may_leave_out_topics(config):
    # R13.7, R14.4: not every topic has to be offered.
    def drop(d):
        svt(d)["feeds"] = [f for f in svt(d)["feeds"] if f["topic"] != "nature"]
    assert validate_sources(mutated(config, drop))


def test_feed_entries_may_share_a_url(config):
    assert validate_sources(copy.deepcopy(config))  # SVT and Sveriges Radio already do (R14.4)
