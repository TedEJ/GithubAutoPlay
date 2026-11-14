"""The build: orchestration and output (R3.2, R3.4, R6.2 to R6.7, R12.1, R13 to R15, R19).

`build(...)` reads `sources.json` and the keyword file of every topic that it names,
fetches every enabled `fetchedBy: build` source through an injected fetch function,
selects the items and writes the output folder:

    <out>/news.json              version 2: items with their topics, status per source and feed
    <out>/<content of site/>     the page (index.html, logic.js, ...)
    <out>/sources.json           copy
    <out>/<topic>-keywords.json  copy of each keyword file named in sources.json

Both "now" and the fetch function are injected, so the tests need neither a
clock nor a network. A fetch function has the signature
`fetch(url, allowed_hosts) -> bytes` and raises `FetchError` on failure.

Each distinct feed address of a source is checked against robots.txt, fetched and
parsed once, however many feed entries (topics) use it (R15.1). A failing address
marks only the feed entries that use it and never stops the other addresses or the
build (R15.2, R19.3). A feed that fails keeps, for up to 24 hours, the items of the
source that have its topic from the previous `news.json` (R19.4).

Failure rules: a failing feed never fails the build (R6.4); only an invalid
`sources.json` or an invalid or missing keyword file does (`BuildError`).
"""
import json
import os
import re
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from .fetch import FetchError
from .keywords import KeywordsError, load_keywords, topics_of
from .model import NewsItem, TopicItem
from .parse import FeedError, parse_rss
from .robots import is_allowed, robots_url, url_path
from .select import (MAX_AGE, MAX_ITEMS, POLITICS, WHITESPACE, check_url, clean_headline, item_id,
                     parse_url, sort_items)
from .timeutil import (UTC, display_time, generated_at, generated_at_display, parse_time,
                       published_utc)

APP_ROOT = Path(__file__).resolve().parent.parent
VERSION = 2  # news.json (R19.1)
FALLBACK_LIMIT = timedelta(hours=24)  # R6.2
METHODS = ("feed", "categoryFilter", "keywordFilter")
SOURCES_VERSION = 2  # R14.1
ALL_NEWS = "all-news"
TOPIC_IDS = (ALL_NEWS, POLITICS, "nature", "ai")  # R13.1, in this order
KEYWORDS_NAME = "{}-keywords.json"  # R14.1; the files are loaded and checked by `load_keyword_files` (R14.5)
KEYWORDS_RE = re.compile(r"^[a-z0-9-]+-keywords\.json$")
# The topics whose feed entries the build fetches and evaluates: all four from F5 (D31, D38).
BUILD_TOPICS = TOPIC_IDS
FETCHED_BY = ("build", "browser")
ITEM_FIELDS = ("id", "sourceId", "sourceName", "title", "url", "published", "publishedDisplay")  # R1.1
ITEM_FIELDS_V2 = ITEM_FIELDS + ("topics",)  # R1.5
STATUS_RANK = {"ok": 0, "blocked-by-robots": 1, "error": 2}  # R19.3: the worst status wins


class EmptyFeed(FeedError):
    """The feed parsed but holds no items (R6.2: a failed fetch)."""


class BuildError(Exception):
    """The build cannot run or must not write (invalid configuration, refused source)."""


# ---------------------------------------------------------------------------
# sources.json

def _require(condition, message):
    if not condition:
        raise BuildError("sources.json: " + message)


def _is_text(value):
    return isinstance(value, str) and value != ""


def _https_host(url):
    """The lower-case host of an https address, or None. As strict as `select.check_url`
    (`parse_url`): no port, user information, backslash, control character or white space."""
    if not isinstance(url, str) or url != url.strip():
        return None
    parsed = parse_url(url)
    return parsed[1] if parsed is not None and parsed[0] == "https" else None


def _on_hosts(host, hosts):
    return any(host == h or host.endswith("." + h) for h in hosts)


def _validate_topics(topics):
    """R14.1: exactly the four topics in order; the keyword file name follows the name rule."""
    _require(isinstance(topics, list) and all(isinstance(t, dict) for t in topics),
             "topics must be a list of objects")
    _require([t.get("id") for t in topics] == list(TOPIC_IDS),
             "topics must be exactly %s, in this order" % ", ".join(TOPIC_IDS))
    for topic in topics:
        where = "topic %r: " % topic["id"]
        _require(_is_text(topic.get("label")), where + "label must be text")
        if topic["id"] == ALL_NEWS:
            _require("keywords" not in topic, where + "must not have keywords")
        else:
            name = topic.get("keywords")
            _require(isinstance(name, str) and name == KEYWORDS_NAME.format(topic["id"])
                     and KEYWORDS_RE.match(name),
                     where + "keywords must be %s" % KEYWORDS_NAME.format(topic["id"]))


def _validate_feeds(where, source, feeds):
    _require(isinstance(feeds, list) and feeds, where + "feeds must be a non-empty list")
    seen = set()
    for number, feed in enumerate(feeds):
        at = where + "feeds[%d]: " % number
        _require(isinstance(feed, dict), at + "must be an object")
        topic = feed.get("topic")
        _require(topic in TOPIC_IDS, at + "topic must be one of %s" % ", ".join(TOPIC_IDS))
        _require(topic not in seen, at + "a second feed for the topic %s" % topic)
        seen.add(topic)
        method = feed.get("method")
        _require(method in METHODS, at + "method must be one of %s" % ", ".join(METHODS))
        _require(topic != ALL_NEWS or method == "feed", at + "the topic all-news only uses the method feed")
        host = _https_host(feed.get("url"))
        _require(host is not None, at + "url must be an https address")
        if source["fetchedBy"] == "build":
            _require(_on_hosts(host, source["allowedHosts"]), at + "the feed address must be on allowedHosts")
        if "matchOn" in feed:
            _require(feed["matchOn"] == "title" and method == "keywordFilter",
                     at + "matchOn is allowed only as \"title\" with the method keywordFilter")


def validate_sources(data):
    """Check the shape and rules of the parsed `sources.json` (version 2, design 7.5) and
    return the list of sources (R14).

    A browser source must have `storageAllowed: false` (R3.2); the feed address of a
    build source must be on its own `allowedHosts` (R6.2, R14.3). Of the keyword files
    only the names are checked, not that they exist (R14.1).
    """
    _require(isinstance(data, dict), "the file must be an object")
    version = data.get("version")
    if version == 1 and type(version) is int:
        raise BuildError("sources.json version 1 is no longer supported")  # R14.6, exact wording
    _require(version == SOURCES_VERSION and type(version) is int, "version must be 2")
    _validate_topics(data.get("topics"))
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
        _require(_https_host(source.get("homepage")) is not None, where + "homepage must be an https address")
        hosts = source.get("allowedHosts")
        _require(isinstance(hosts, list) and hosts and all(
            _is_text(h) and h == h.lower() and "/" not in h for h in hosts),
            where + "allowedHosts must be a list of lower-case host names")
        if "credit" in source:
            _require(_is_text(source["credit"]), where + "credit must be non-empty text")
        if "linkHosts" in source:
            link_hosts = source["linkHosts"]
            _require(isinstance(link_hosts, list) and link_hosts and all(
                _is_text(h) and h == h.lower() and "/" not in h and _on_hosts(h, hosts) for h in link_hosts),
                where + "linkHosts must be a non-empty list of lower-case host names on allowedHosts")
        if source["fetchedBy"] == "browser":
            _require(source["storageAllowed"] is False, where + "a browser source must have storageAllowed false (R3.2)")
        else:
            _require(source["storageAllowed"] is True, where + "a build source must have storageAllowed true")
        _validate_feeds(where, source, source.get("feeds"))
    return sources


def distinct_feed_urls(source, topics=None):
    """The distinct feed addresses of `source` for `topics`, in the order of its `feeds`.

    Feed entries that share an address count once (R15.1): the build fetches each of
    these addresses once. `topics` defaults to `BUILD_TOPICS`."""
    topics = BUILD_TOPICS if topics is None else topics
    urls = []
    for feed in source["feeds"]:
        if feed["topic"] in topics and feed["url"] not in urls:
            urls.append(feed["url"])
    return urls


def load_configuration(path):
    """Read and validate `sources.json`: returns (topics, sources), `topics` being the
    list of topic objects (`id`, `label`, optional `keywords`) in order (R14.1)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BuildError("sources.json: cannot read: %s" % exc) from exc
    sources = validate_sources(data)
    return data["topics"], sources


def load_sources(path):
    return load_configuration(path)[1]


def load_keyword_files(root, topics):
    """The keyword list of every topic that names a file (R14.5, R17.5): topic id -> `Keywords`.

    The file must exist in `root`, belong to the topic and be valid; otherwise the
    build fails with a message that names the file (R6.4). `all-news` has none."""
    keywords = {}
    for topic in topics:
        name = topic.get("keywords")
        if name is None:
            continue
        if not (Path(root) / name).is_file():
            raise BuildError("%s: file not found (sources.json names it for the topic %s)" % (name, topic["id"]))
        try:
            keywords[topic["id"]] = load_keywords(Path(root) / name, topic["id"])
        except KeywordsError as exc:
            raise BuildError("%s: %s" % (name, exc)) from exc
    return keywords


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
    """The previous `news.json` as a dict (version 1 or 2), or None if it is missing or unusable."""
    if path is None:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] not in (1, 2) \
            or not isinstance(data.get("sources"), list) or not isinstance(data.get("items"), list):
        return None
    return data


def _previous_entry(previous, source_id):
    if previous is None:
        return None
    for entry in previous["sources"]:
        if isinstance(entry, dict) and entry.get("id") == source_id:
            return entry
    return None


def _success_of(entry):
    """(aware datetime, original text) of the `lastSuccess` of a previous source or feed
    entry, or (None, None)."""
    text = entry.get("lastSuccess") if isinstance(entry, dict) else None
    moment = parse_time(text) if isinstance(text, str) else None
    return (moment, text) if moment is not None else (None, None)


def _previous_feed_success(previous, source_id, topic):
    """The previous `lastSuccess` of the feed of `topic` of this source (R19.4), or (None, None).

    A version 1 file has no feeds: its source entry stands for the feed `politics`, and the
    other feeds have no previous items."""
    entry = _previous_entry(previous, source_id)
    if entry is None:
        return None, None
    if previous["version"] == 1:
        return _success_of(entry) if topic == POLITICS else (None, None)
    feeds = entry.get("feeds")
    if isinstance(feeds, list):
        for feed in feeds:
            if isinstance(feed, dict) and feed.get("topic") == topic:
                return _success_of(feed)
    return None, None


def _read_topics(value):
    """A non-empty list of known topic ids -> the tuple in the order of R13.1 without
    duplicates, else None."""
    if not isinstance(value, list) or not value or not all(isinstance(t, str) and t in TOPIC_IDS for t in value):
        return None
    return tuple(t for t in TOPIC_IDS if t in value)


def _previous_items(previous, source, now):
    """Valid previous items of this source as (normalised URL, `NewsItem`, set of topics), rebuilt
    with the current rules.

    Items older than 7 days before `now` are dropped (R5.2), as in a fresh build. A version 1
    item has the topic `politics` only (R19.4). The cap is applied later, per topic (R13.6)."""
    items = []
    cutoff = now.astimezone(UTC) - MAX_AGE
    fields = set(ITEM_FIELDS_V2 if previous["version"] == 2 else ITEM_FIELDS)
    for raw in previous["items"]:
        if not isinstance(raw, dict) or set(raw) != fields or raw["sourceId"] != source["id"]:
            continue
        topics = _read_topics(raw["topics"]) if previous["version"] == 2 else (POLITICS,)
        title, url, published = raw["title"], raw["url"], raw["published"]
        if topics is None or not (isinstance(title, str) and title.strip() and isinstance(url, str)):
            continue
        normalised = check_url(url, source["allowedHosts"])
        if normalised is None:
            continue
        if published is not None:
            moment = parse_time(published) if isinstance(published, str) else None
            if moment is None or moment < cutoff:
                continue
        try:
            shown = display_time(published)
        except ValueError:
            continue
        items.append((normalised, NewsItem(item_id(normalised), source["id"], source["name"], title,
                                           url.strip(), published, shown), set(topics)))
    return items


# ---------------------------------------------------------------------------
# one source

class RobotsUnreadable(Exception):
    """robots.txt could not be read, so the source is not fetched (status error)."""


class _Robots:
    """robots.txt of each host, read once per run (R6.6).

    Answer 200: the rules are applied. Status 404 or another 4xx except 429:
    no rules, everything is allowed. Anything else (timeout, network error,
    5xx, 429, a response over 2 MiB, text that is not UTF-8, a redirect to
    another host): `RobotsUnreadable`, and the source is not fetched.
    """

    def __init__(self, fetch, user_agent):
        self.fetch = fetch
        self.user_agent = user_agent
        self.cache = {}  # robots.txt address -> text ("" = no rules) or RobotsUnreadable

    def _read(self, url, allowed_hosts):
        try:
            return self.fetch(url, allowed_hosts).decode("utf-8-sig")  # a byte order mark is dropped
        except FetchError as exc:
            if exc.kind == "status" and exc.status is not None and 400 <= exc.status < 500 and exc.status != 429:
                return ""
            raise RobotsUnreadable("robots.txt could not be read: %s" % exc) from exc
        except UnicodeDecodeError as exc:
            raise RobotsUnreadable("robots.txt could not be read: not UTF-8 text") from exc
        except Exception as exc:  # a fetch layer must not break the build
            raise RobotsUnreadable("robots.txt could not be read (%s)" % type(exc).__name__) from exc

    def allowed(self, feed_url, allowed_hosts):
        url = robots_url(feed_url)
        if url not in self.cache:
            try:
                self.cache[url] = self._read(url, allowed_hosts)
            except RobotsUnreadable as exc:
                self.cache[url] = exc
        text = self.cache[url]
        if isinstance(text, RobotsUnreadable):
            raise text
        return is_allowed(text, self.user_agent, url_path(feed_url))


def _fetch_entries(url, allowed_hosts, fetch):
    """The parsed entries of one feed address, or raises FetchError, FeedError."""
    try:
        body = fetch(url, allowed_hosts)
    except FetchError:
        raise
    except Exception as exc:  # a fetch layer must not break the build
        raise FetchError("network", "fetch failed (%s)" % type(exc).__name__) from exc
    entries = parse_rss(body)
    if not entries:
        raise EmptyFeed("the feed has no items")
    return entries


class _Outcome:
    """What happened to one feed address: its status, a message (never feed content) and,
    when it was read, its raw entries."""

    def __init__(self, status, message=None, entries=None):
        self.status, self.message, self.entries = status, message, entries


def _read_feed(url, allowed_hosts, fetch, robots):
    """Check robots.txt, fetch and parse one feed address (R6.2, R6.6). Never raises."""
    try:
        robots_ok = robots.allowed(url, allowed_hosts)
    except RobotsUnreadable as exc:
        return _Outcome("error", str(exc))
    if robots_ok is False:
        return _Outcome("blocked-by-robots", "robots.txt does not allow this address")
    try:
        return _Outcome("ok", entries=_fetch_entries(url, allowed_hosts, fetch))
    except FetchError as exc:
        return _Outcome("error", "fetch failed: %s" % exc)
    except EmptyFeed:
        return _Outcome("error", "feed not usable: it has no items")
    except FeedError:
        # No detail from the parser: its text may quote the feed.
        return _Outcome("error", "feed not usable (FeedError)")


def _evaluate_feed(entries, feeds, source, keywords_by_topic, now):
    """The items of one parsed feed address for the feed entries that use it.

    Returns a list of (normalised URL, `NewsItem` without topics, set of topics) in feed order. An
    entry is dropped for an empty headline (R1.4), an unusable link (R1.4, R9.1), no topic (R13.3)
    or a time more than 7 days back (R5.2). `topics_of` takes the raw texts and cleans them itself
    (R13.4). Raises ValueError for an unsupported method (`categoryFilter`) before anything is
    evaluated."""
    for feed in feeds:
        if feed["method"] not in ("feed", "keywordFilter"):
            raise ValueError("unsupported method %r for topic %s" % (feed["method"], feed["topic"]))
    cutoff = now.astimezone(UTC) - MAX_AGE
    result = []
    for entry in entries:
        title = clean_headline(entry.title)
        if title == "":
            continue
        normalised = check_url(entry.link, source["allowedHosts"])
        if normalised is None:
            continue
        topics = topics_of(entry.title, entry.description, feeds, keywords_by_topic)
        if not topics:
            continue
        published = published_utc(entry.time_text, now)
        if published is not None and parse_time(published) < cutoff:
            continue  # too old; a fresher copy of the same article from another feed can still count
        result.append((normalised, NewsItem(item_id(normalised), source["id"], source["name"], title,
                                            entry.link.strip(WHITESPACE), published, display_time(published)),
                       set(topics)))
    return result


def build_source(source, keywords_by_topic, now, fetch, robots, previous):
    """Handle one build source. Returns (status entry for `news.json`, list of `TopicItem`).

    Each distinct feed address of the topics in `BUILD_TOPICS` is checked against robots.txt,
    fetched and parsed once, however many feed entries use it (R15.1), and a failing address
    does not stop the others (R15.2). Every feed entry is evaluated on the response of its
    address (R13.3); an item that comes from several addresses, or matches several topics,
    becomes one item with all its topics (R13.5). The age limit and the cap of 20 are applied per
    topic (R13.6). A feed that failed with status `error` keeps the items of this source that
    have its topic from the previous file, if its previous `lastSuccess` is under 24 hours old
    (R19.4); a blocked feed keeps nothing."""
    assert_storable(source)
    ok_time = generated_at(now)
    feeds = [f for f in source["feeds"] if f["topic"] in BUILD_TOPICS]

    outcomes = {}
    for url in distinct_feed_urls(source):
        outcomes[url] = _read_feed(url, source["allowedHosts"], fetch, robots)

    # found: normalised URL -> [item, set of topics]; the first occurrence that is not too old (feed
    # addresses in the order of sources.json, then feed order) gives headline, link and time.
    found = {}
    for url, outcome in outcomes.items():
        if outcome.status != "ok":
            continue
        url_feeds = [f for f in feeds if f["url"] == url]
        try:
            evaluated = _evaluate_feed(outcome.entries, url_feeds, source, keywords_by_topic, now)
        except ValueError:  # an unsupported method, such as categoryFilter
            bad = next((f for f in url_feeds if f["method"] not in ("feed", "keywordFilter")), None)
            outcome.status = "error"
            outcome.message = "selection failed (ValueError)" + (
                ", %s method %s" % (bad["topic"], bad["method"]) if bad else "")
            continue
        for normalised, item, topics in evaluated:
            if normalised in found:
                found[normalised][1] |= topics
            else:
                found[normalised] = [item, set(topics)]

    # The status and the fallback of each feed entry (R19.3, R19.4).
    feed_info = []  # (feed entry, status, message, lastSuccess datetime, lastSuccess text)
    fallback_topics = set()
    for feed in feeds:
        outcome = outcomes[feed["url"]]
        if outcome.status == "ok":
            feed_info.append((feed, "ok", None, parse_time(ok_time), ok_time))
            continue
        moment, text = _previous_feed_success(previous, source["id"], feed["topic"])
        feed_info.append((feed, outcome.status, outcome.message, moment, text))
        if outcome.status == "error" and moment is not None:
            if timedelta(0) <= now.astimezone(UTC) - moment < FALLBACK_LIMIT:  # R19.4
                fallback_topics.add(feed["topic"])
    if fallback_topics and previous is not None:
        for normalised, item, previous_topics in _previous_items(previous, source, now):
            topics = previous_topics & fallback_topics
            if not topics:
                continue
            if normalised in found:
                found[normalised][1] |= topics
            else:
                found[normalised] = [item, topics]

    # The age limit is applied above; now the cap per topic (R13.6).
    kept = {}  # item id -> topics in which the item was kept
    for topic in TOPIC_IDS:
        for item in sort_items([entry[0] for entry in found.values() if topic in entry[1]])[:MAX_ITEMS]:
            kept.setdefault(item.id, set()).add(topic)
    ordered = sort_items([entry[0] for entry in found.values() if entry[0].id in kept])
    items = [TopicItem.of(item, [t for t in TOPIC_IDS if t in kept[item.id]]) for item in ordered]

    feed_entries = []
    for feed, status, message, _moment, text in feed_info:
        entry = {"topic": feed["topic"], "status": status, "lastSuccess": text,
                 "itemCount": sum(1 for item in items if feed["topic"] in item.topics)}
        if status != "ok":
            entry["message"] = message
        feed_entries.append(entry)

    # The source: the worst status, the oldest lastSuccess, the first message of that status (R19.3).
    worst = max((info[1] for info in feed_info), key=STATUS_RANK.__getitem__, default="ok")
    moments = [info[3] for info in feed_info]
    oldest = None
    if feed_info and all(m is not None for m in moments):
        oldest = min(feed_info, key=lambda info: info[3])[4]
    elif not feed_info:
        oldest = ok_time
    entry = {"id": source["id"], "name": source["name"], "status": worst, "lastSuccess": oldest,
             "itemCount": len(items)}
    if worst != "ok":
        entry["message"] = next(info[2] for info in feed_info if info[1] == worst)
    entry["feeds"] = feed_entries
    return entry, items


# ---------------------------------------------------------------------------
# output

SITE_SKIP_NAMES = ("__pycache__", "node_modules")


def _same(a, b):
    """True if two existing paths are the same file or folder (also across case and links)."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _check_output_folder(out, root):
    out, root = Path(out), Path(root)
    if out.is_symlink():
        raise BuildError("the output folder %s is a symbolic link" % out)
    if out.exists() and not out.is_dir():
        raise BuildError("the output folder %s is not a folder" % out)
    site = (root / "site").resolve()  # follows a symbolic link
    # The nearest folder that exists decides: a new folder inside site/ is refused too.
    nearest = out
    while not nearest.exists():
        nearest = nearest.parent
    if any(_same(site, q) for q in [nearest, *nearest.resolve().parents]):
        raise BuildError("the output folder %s overlaps site/" % out)
    if out.exists() and (_same(out, root) or any(_same(out, q) for q in root.resolve().parents)):
        raise BuildError("the output folder %s overlaps the project folder" % out)


def _planned_files(root, keyword_names):
    """(source file, path relative to the output folder) for everything that is copied.

    The content of `site/` (without its `tests` folder, `__pycache__`,
    `node_modules` and symbolic links), `sources.json` and the keyword files named in it (R14.5)."""
    plan = []
    site = (root / "site").resolve()
    if site.is_dir():
        for path in sorted(site.rglob("*")):
            relative = path.relative_to(site)
            if path.is_symlink() or not path.is_file() or relative.parts[0] == "tests" or any(
                    part in SITE_SKIP_NAMES for part in relative.parts):
                continue
            plan.append((path, relative))
    for name in ("sources.json", *keyword_names):
        plan.append((root / name, Path(name)))
    return plan


def _check_targets(out, relatives):
    """Refuse to write through a symbolic link: no target, no temporary file, and no
    folder on the way may be one."""
    for relative in relatives:
        for name in (relative, relative.with_name(relative.name + ".tmp")):
            if (out / name).is_symlink():
                raise BuildError("refusing to write through the symbolic link %s" % (out / name))
        for parent in relative.parents:
            if (out / parent).is_symlink():
                raise BuildError("refusing to write through the symbolic link %s" % (out / parent))


def _replace_file(target, data):
    """Write `data` to a new temporary file next to `target` and rename it onto `target`.

    The old file is replaced, never written into, so a hard link to it keeps its content."""
    temporary = target.with_name(target.name + ".tmp")
    temporary.unlink(missing_ok=True)
    with open(temporary, "xb") as handle:  # exclusive: never follows a link
        handle.write(data)
    os.replace(temporary, target)


def _write_json(path, document):
    _replace_file(path, (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _check_document(document, sources, topic_ids):
    """Last guard before writing (R19.6): only storable build sources (N10, R3.2), and the shape
    of R19.1 to R19.3, so a bug in the build cannot write a file that the page refuses."""
    storable = {s["id"] for s in sources if s["fetchedBy"] == "build" and s["storageAllowed"] is True}
    for entry in document["sources"]:
        if entry["id"] not in storable:
            raise BuildError("refusing to write source %r to news.json" % entry["id"])
    for item in document["items"]:
        if item["sourceId"] not in storable:
            raise BuildError("refusing to write an item of source %r to news.json" % item["sourceId"])
    problem = None
    if document.get("version") != VERSION or document.get("topics") != list(topic_ids):
        problem = "version or topics"
    for entry in document["sources"]:
        if entry.get("status") not in STATUS_RANK or not isinstance(entry.get("feeds"), list) \
                or ("message" in entry) != (entry.get("status") != "ok"):
            problem = "source %r" % entry["id"]
        for feed in entry.get("feeds") or []:
            if feed.get("topic") not in topic_ids or feed.get("status") not in STATUS_RANK \
                    or ("message" in feed) != (feed.get("status") != "ok"):
                problem = "a feed of source %r" % entry["id"]
    ids = set()
    for item in document["items"]:
        topics = item.get("topics")
        if set(item) != set(ITEM_FIELDS_V2) or not isinstance(topics, list) or not topics \
                or topics != [t for t in topic_ids if t in topics] or len(set(topics)) != len(topics) \
                or (item["sourceId"], item["id"]) in ids:
            problem = "item %r" % item.get("id")
        ids.add((item["sourceId"], item.get("id")))
    if problem:
        raise BuildError("internal error: news.json does not follow R19.1 to R19.3 (%s); nothing was written" % problem)


def build(out, now, fetch, previous_path=None, root=APP_ROOT, user_agent=None):
    """Run the whole build into the folder `out` and return the `news.json` document.

    `previous_path` defaults to `<out>/news.json` when that file exists (R12.1).
    Raises `BuildError` for an invalid configuration; nothing is written then.
    """
    from .fetch import USER_AGENT
    user_agent = user_agent or USER_AGENT
    root, out = Path(root), Path(out)
    topics, sources = load_configuration(root / "sources.json")
    keywords = load_keyword_files(root, topics)  # a missing or invalid file fails the build (R14.5, R17.5)
    _check_output_folder(out, root)

    if previous_path is None:
        previous_path = out / "news.json"
    previous = load_previous(previous_path)  # read before anything is overwritten

    topic_ids = [t["id"] for t in topics]
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
        "topics": topic_ids,
        "sources": entries,
        "items": [i.as_dict() for i in items],
    }
    _check_document(document, sources, topic_ids)

    plan = _planned_files(root, [t["keywords"] for t in topics if "keywords" in t])
    _check_targets(out, [Path("news.json")] + [rel for _, rel in plan])
    out.mkdir(parents=True, exist_ok=True)
    _write_json(out / "news.json", document)
    for source_file, relative in plan:
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _replace_file(target, source_file.read_bytes())
    return document
