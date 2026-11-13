"""Validates sources.json against the rules in news-reader-design.md (R3, R4, 7.1)."""
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parent.parent
METHODS = {"feed", "categoryFilter", "keywordFilter"}
FETCHED_BY = {"build", "browser"}
ID_ORDER = ["svt", "sveriges-radio"]


@pytest.fixture(scope="module")
def config():
    return json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sources(config):
    return config["sources"]


def test_version(config):
    assert config["version"] == 1


def test_exactly_the_two_approved_sources(sources):
    assert [s["id"] for s in sources] == ID_ORDER
    assert [s["name"] for s in sources] == ["SVT", "Sveriges Radio"]


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


def test_each_source_has_exactly_one_politics_method(sources):
    for s in sources:
        category = s["politics-sweden"]
        assert category["method"] in METHODS
        assert urlparse(category["url"]).scheme == "https"


def test_urls_are_on_allowed_hosts_for_build_sources(sources):
    # The feed URL of a build source must be on its allowed hosts (R6.2).
    for s in sources:
        if s["fetchedBy"] == "build":
            host = urlparse(s["politics-sweden"]["url"]).hostname
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
    assert sr["politics-sweden"]["url"] == "https://api.sr.se/api/rss/program/83"


def test_svt_is_collected_by_the_build(sources):
    svt = next(s for s in sources if s["id"] == "svt")
    assert svt["fetchedBy"] == "build"
    assert svt["storageAllowed"] is True
    assert svt["politics-sweden"]["url"] == "https://www.svt.se/nyheter/inrikes/rss.xml"


def test_shared_cases_has_the_three_sections():
    # Created empty in S2; later steps fill the sections, so only the shape is checked.
    cases = json.loads((ROOT / "tests" / "shared-cases.json").read_text(encoding="utf-8"))
    assert set(cases) == {"cleaning", "time", "keywords"}
    assert all(isinstance(v, list) for v in cases.values())
