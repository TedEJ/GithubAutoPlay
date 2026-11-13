"""Helpers for the build tests: a fake fetch layer and invented sources and feeds.

Nothing here touches the network. Hosts are `*.example.invalid`, headlines are invented.
"""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from newsreader.fetch import FetchError

APP = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
FEED_URL = "https://news.example.invalid/politics/rss.xml"
ROBOTS_URL = "https://news.example.invalid/robots.txt"
BROWSER_FEED_URL = "https://live.example.invalid/atom.xml"


def source(**changes):
    entry = {
        "id": "test-news", "name": "Test News", "enabled": True, "fetchedBy": "build",
        "storageAllowed": True, "homepage": "https://news.example.invalid/",
        "allowedHosts": ["example.invalid"],
        "politics-sweden": {"method": "keywordFilter", "url": FEED_URL},
    }
    entry.update(changes)
    return entry


def browser_source(**changes):
    entry = source(id="live-radio", name="Live Radio", fetchedBy="browser", storageAllowed=False)
    entry["politics-sweden"] = {"method": "keywordFilter", "url": BROWSER_FEED_URL}
    entry.update(changes)
    return entry


def rss(*items):
    """items: (title, path, pubDate) tuples -> RSS 2.0 bytes."""
    body = "".join(
        "<item><title>%s</title><link>https://news.example.invalid%s</link><pubDate>%s</pubDate>"
        "<description>Invented description</description></item>" % item for item in items)
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>x</title>%s'
            "</channel></rss>" % body).encode("utf-8")


GOOD_FEED = rss(
    ("Riksdagen debatterar exempelfrågan", "/a/1", "Fri, 13 Nov 2026 11:00:00 GMT"),
    ("Regeringen presenterar ett påhittat förslag", "/a/2", "Fri, 13 Nov 2026 10:00:00 GMT"),
    ("Vädret blir fint i helgen", "/a/3", "Fri, 13 Nov 2026 09:00:00 GMT"),
)


class FakeFetch:
    """A fake fetch layer: maps a URL to bytes, an exception, or a function (url -> bytes)."""

    def __init__(self, responses=None):
        self.responses = dict(responses or {})
        self.calls = []

    def __call__(self, url, allowed_hosts):
        self.calls.append(url)
        if url not in self.responses:
            raise FetchError("status", "HTTP status 404", 404)
        response = self.responses[url]
        if callable(response):
            response = response(url)
        if isinstance(response, Exception):
            raise response
        return response


