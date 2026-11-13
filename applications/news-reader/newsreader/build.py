"""The build: orchestration and output (R3.2, R3.4, R6.2 to R6.7, R12.1).

`build(...)` reads `sources.json` and `politics-keywords.json`, fetches every
enabled `fetchedBy: build` source through an injected fetch function, selects
the items and writes the output folder:

    <out>/news.json              the items and the status of each build source
    <out>/<content of site/>     the page (index.html, logic.js, ...)
    <out>/sources.json           copy
    <out>/politics-keywords.json copy

Both "now" and the fetch function are injected, so the tests need neither a
clock nor a network. A fetch function has the signature
`fetch(url, allowed_hosts) -> bytes` and raises `FetchError` on failure.

Failure rules: a failing source never fails the build (R6.4); only an invalid
`sources.json` or `politics-keywords.json` does (`BuildError`). A source that
fails keeps its items from the previous `news.json` for up to 24 hours (R6.2).
"""
import json
import os
import shutil
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from .fetch import FetchError
from .keywords import KeywordsError, load_keywords
from .model import NewsItem
from .parse import FeedError, parse_rss
from .robots import is_allowed, robots_url, url_path
from .select import MAX_ITEMS, check_url, item_id, select_items
from .timeutil import UTC, display_time, generated_at, generated_at_display, parse_time

APP_ROOT = Path(__file__).resolve().parent.parent
CATEGORY = "politics-sweden"
VERSION = 1
FALLBACK_LIMIT = timedelta(hours=24)  # R6.2
METHODS = ("feed", "categoryFilter", "keywordFilter")
FETCHED_BY = ("build", "browser")
ITEM_FIELDS = ("id", "sourceId", "sourceName", "title", "url", "published", "publishedDisplay")


class BuildError(Exception):
    """The build cannot run or must not write (invalid configuration, refused source)."""


# ---------------------------------------------------------------------------
# sources.json

def _require(condition, message):
    if not condition:
        raise BuildError("sources.json: " + message)


def _is_text(value):
    return isinstance(value, str) and value != ""


def validate_sources(data):
    """Check the shape and rules of the parsed `sources.json` (design 7.1) and return the list.

    A browser source must have `storageAllowed: false` (R3.2); a build source
    must have its feed URL on its own `allowedHosts` (R6.2).
    """
    _require(isinstance(data, dict), "the file must be an object")
    _require(data.get("version") == 1 and type(data.get("version")) is int, "version must be 1")
    sources = data.get("sources")
    _require(isinstance(sources, list) and sources, "sources must be a non-empty list")
    seen = set()
    for index, source in enumerate(sources):
        _require(isinstance(source, dict), "source %d must be an object" % index)
        sid = source.get("id")
        _require(_is_text(sid), "source %d has no id" % index)
        where = "source %r: " % sid
        _require(sid not in seen, where + "duplicate id")
        seen.add(sid)
        _require(_is_text(source.get("name")), where + "name must be text")
        _require(isinstance(source.get("enabled"), bool), where + "enabled must be true or false")
        _require(source.get("fetchedBy") in FETCHED_BY, where + "fetchedBy must be build or browser")
        _require(isinstance(source.get("storageAllowed"), bool), where + "storageAllowed must be true or false")
        hosts = source.get("allowedHosts")
        _require(isinstance(hosts, list) and hosts and all(
            _is_text(h) and h == h.lower() and "/" not in h for h in hosts),
            where + "allowedHosts must be a list of lower-case host names")
        method = source.get("politics-sweden")
        _require(isinstance(method, dict) and method.get("method") in METHODS,
                 where + "politics-sweden.method must be one of %s" % ", ".join(METHODS))
        url = method.get("url")
        _require(_is_text(url) and urlsplit(url).scheme == "https" and urlsplit(url).hostname,
                 where + "politics-sweden.url must be an https address")
        if source["fetchedBy"] == "browser":
            _require(source["storageAllowed"] is False, where + "a browser source must have storageAllowed false (R3.2)")
        else:
            _require(source["storageAllowed"] is True, where + "a build source must have storageAllowed true")
            host = urlsplit(url).hostname.lower()
            _require(any(host == h or host.endswith("." + h) for h in hosts),
                     where + "the feed address must be on allowedHosts")
    return sources


def load_sources(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BuildError("sources.json: cannot read: %s" % exc) from exc
    return validate_sources(data)


def build_sources(sources):
    """The sources the build handles: enabled (R3.4) and `fetchedBy: build` (R6.7, R3.2)."""
    return [s for s in sources if s["enabled"] and s["fetchedBy"] == "build"]


def assert_storable(source):
    """Refuse any source that may not be fetched or stored by the build (N10, R3.2, R6.7)."""
    if source.get("fetchedBy") != "build" or source.get("storageAllowed") is not True:
        raise BuildError("refusing source %r: it is not a build source that may be stored" % source.get("id"))


# ---------------------------------------------------------------------------
# previous news.json (the 24-hour fallback)

def load_previous(path):
    """The previous `news.json` as a dict, or None if it is missing or unusable."""
    if path is None:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("sources"), list) \
            or not isinstance(data.get("items"), list):
        return None
    return data


def _previous_entry(previous, source_id):
    if previous is None:
        return None
    for entry in previous["sources"]:
        if isinstance(entry, dict) and entry.get("id") == source_id:
            return entry
    return None


def _previous_success(entry):
    """The last-success time (aware datetime) of a previous source entry, or None."""
    text = entry.get("lastSuccess") if entry else None
    return parse_time(text) if isinstance(text, str) else None


def _previous_items(previous, source):
    """Valid previous items of this source, rebuilt with the current rules."""
    items = []
    for raw in previous["items"]:
        if not isinstance(raw, dict) or set(raw) != set(ITEM_FIELDS) or raw["sourceId"] != source["id"]:
            continue
        title, url, published = raw["title"], raw["url"], raw["published"]
        if not (isinstance(title, str) and title.strip() and isinstance(url, str)):
            continue
        normalised = check_url(url, source["allowedHosts"])
        if normalised is None:
            continue
        if published is not None:
            if not isinstance(published, str) or parse_time(published) is None:
                continue
        try:
            shown = display_time(published)
        except ValueError:
            continue
        items.append(NewsItem(item_id(normalised), source["id"], source["name"], title, url.strip(), published, shown))
    return items[:MAX_ITEMS]


# ---------------------------------------------------------------------------
# one source

class _Robots:
    """robots.txt of each host, read once per run (R6.6).

    A robots.txt that is missing or cannot be read allows the fetch (owner
    decision for issue #72; the design text of R6.6 said the opposite).
    """

    def __init__(self, fetch, user_agent):
        self.fetch = fetch
        self.user_agent = user_agent
        self.cache = {}

    def allowed(self, feed_url, allowed_hosts):
        url = robots_url(feed_url)
        if url not in self.cache:
            try:
                self.cache[url] = self.fetch(url, allowed_hosts).decode("utf-8", errors="replace")
            except Exception:  # any failure: no usable robots.txt
                self.cache[url] = None
        text = self.cache[url]
        return True if text is None else is_allowed(text, self.user_agent, url_path(feed_url))


def _fetch_and_select(source, keywords, now, fetch):
    """Items of a source, or raises FetchError, FeedError or ValueError."""
    url = source["politics-sweden"]["url"]
    try:
        body = fetch(url, source["allowedHosts"])
    except FetchError:
        raise
    except Exception as exc:  # a fetch layer must not break the build
        raise FetchError("network", "fetch failed (%s)" % type(exc).__name__) from exc
    entries = parse_rss(body)
    if not entries:
        raise FeedError("the feed has no items")
    return select_items(entries, source, keywords, now)


def build_source(source, keywords, now, fetch, robots, previous):
    """Handle one build source. Returns (status entry for `news.json`, list of NewsItem)."""
    assert_storable(source)
    ok_time = generated_at(now)
    previous_entry = _previous_entry(previous, source["id"])
    last_success = _previous_success(previous_entry)
    last_text = previous_entry["lastSuccess"] if last_success is not None else None
    url = source["politics-sweden"]["url"]

    status, message, items = "ok", None, None
    if not robots.allowed(url, source["allowedHosts"]):
        status, message = "blocked-by-robots", "robots.txt does not allow this address"
    else:
        try:
            items = _fetch_and_select(source, keywords, now, fetch)
        except FetchError as exc:
            status, message = "error", "fetch failed: %s" % exc
        except FeedError as exc:
            status, message = "error", "feed not usable: %s" % exc
        except ValueError as exc:  # select_items: unsupported method, such as categoryFilter
            status, message = "error", "selection failed: %s" % exc

    if status == "ok":
        entry = {"id": source["id"], "name": source["name"], "status": "ok",
                 "lastSuccess": ok_time, "itemCount": len(items)}
        return entry, items

    items = []
    if status == "error" and last_success is not None:
        age = now.astimezone(UTC) - last_success
        if timedelta(0) <= age < FALLBACK_LIMIT:  # R6.2: only items under 24 hours old
            items = _previous_items(previous, source)
    entry = {"id": source["id"], "name": source["name"], "status": status,
             "lastSuccess": last_text, "itemCount": len(items), "message": message}
    return entry, items


# ---------------------------------------------------------------------------
# output

def _check_output_folder(out, root):
    out, root = Path(out).resolve(), Path(root).resolve()
    site = root / "site"
    if out == root or out == site or site in out.parents or out in root.parents:
        raise BuildError("the output folder %s overlaps the project folder" % out)
    if out.exists() and not out.is_dir():
        raise BuildError("the output folder %s is not a folder" % out)


def _write_json(path, document):
    text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _check_document(document, sources):
    """Last guard before writing: only storable build sources, nothing else (N10, R3.2)."""
    storable = {s["id"] for s in sources if s["fetchedBy"] == "build" and s["storageAllowed"] is True}
    for entry in document["sources"]:
        if entry["id"] not in storable:
            raise BuildError("refusing to write source %r to news.json" % entry["id"])
    for item in document["items"]:
        if item["sourceId"] not in storable:
            raise BuildError("refusing to write an item of source %r to news.json" % item["sourceId"])


def build(out, now, fetch, previous_path=None, root=APP_ROOT, user_agent=None):
    """Run the whole build into the folder `out` and return the `news.json` document.

    `previous_path` defaults to `<out>/news.json` when that file exists (R12.1).
    Raises `BuildError` for an invalid configuration; nothing is written then.
    """
    from .fetch import USER_AGENT
    user_agent = user_agent or USER_AGENT
    root, out = Path(root), Path(out)
    sources = load_sources(root / "sources.json")
    try:
        keywords = load_keywords(root / "politics-keywords.json")
    except KeywordsError as exc:
        raise BuildError("politics-keywords.json: %s" % exc) from exc
    _check_output_folder(out, root)

    if previous_path is None:
        previous_path = out / "news.json"
    previous = load_previous(previous_path)  # read before anything is overwritten

    robots = _Robots(fetch, user_agent)
    entries, items = [], []
    for source in build_sources(sources):
        entry, source_items = build_source(source, keywords, now, fetch, robots, previous)
        entries.append(entry)
        items.extend(source_items)

    document = {
        "version": VERSION,
        "generatedAt": generated_at(now),
        "generatedAtDisplay": generated_at_display(now),
        "category": CATEGORY,
        "sources": entries,
        "items": [i.as_dict() for i in items],
    }
    _check_document(document, sources)

    out.mkdir(parents=True, exist_ok=True)
    _write_json(out / "news.json", document)
    site = root / "site"
    if site.is_dir():
        shutil.copytree(site, out, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
    for name in ("sources.json", "politics-keywords.json"):
        shutil.copyfile(root / name, out / name)
    return document
