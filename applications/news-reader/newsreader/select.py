"""Headline cleaning (R1.3) and item selection (R1.1, R1.4, R5.1 to R5.4, R9.1).
No I/O; "now" is always passed in.

Everything is defined with fixed sets and explicit rules, so the JavaScript
version (S9) can reproduce it exactly. Nothing here depends on Python's `html`
module or on `urllib` (see `parse_url`).
"""
import hashlib
import re
from datetime import timedelta

from newsreader.model import NewsItem
from newsreader.timeutil import UTC, display_time, parse_time, published_utc

# `<` followed by a letter (or `/`, `!--`) starts a tag, so "a < b" stays as it is.
# A tag, or the start of a comment (`<!--`, handled in `_strip_markup`).
_TAG_OR_COMMENT_START = re.compile(r"</?[A-Za-z][^<>]*>|<!--")

# White space: U+0020, tab, LF, CR, FF, VT and U+00A0 (no-break space).
# JavaScript must use exactly this set, not trim() or \s.
WHITESPACE = " \t\n\r\f\v "
_WHITESPACE_RUN = re.compile("[" + WHITESPACE + "]+")

# Entities that are decoded: the five XML entities and this small named list.
# Every other named entity, and every entity without a semicolon, is left as written.
NAMED_ENTITIES = {
    "amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'",
    "nbsp": " ", "laquo": "«", "raquo": "»",
    "ndash": "–", "mdash": "—", "hellip": "…",
    "lsquo": "‘", "rsquo": "’", "ldquo": "“", "rdquo": "”",
    "auml": "ä", "ouml": "ö", "aring": "å",
    "Auml": "Ä", "Ouml": "Ö", "Aring": "Å",
    "eacute": "é", "Eacute": "É", "euro": "€", "copy": "©",
}

# `&name;`, `&#123;` or `&#x1F;`. ASCII digits only.
_ENTITY = re.compile(r"&(?:#([0-9]+)|#[xX]([0-9A-Fa-f]+)|([A-Za-z][A-Za-z0-9]*));")


def _decode_entity(match):
    dec, hexa, name = match.groups()
    if name is not None:
        return NAMED_ENTITIES.get(name, match.group(0))
    # Strip leading zeros, then leave a number that is surely above U+10FFFF
    # (over 7 decimal or 6 hex digits) alone, so `int` never sees a huge string.
    digits = (dec if dec is not None else hexa).lstrip("0")
    if len(digits) > (7 if dec is not None else 6):
        return match.group(0)
    code = int(digits or "0", 10 if dec is not None else 16)
    # Valid code points only: not 0, not a surrogate, not above U+10FFFF.
    # &#128; is the plain control character U+0080 (not the euro sign).
    if code == 0 or 0xD800 <= code <= 0xDFFF or code > 0x10FFFF:
        return match.group(0)
    return chr(code)


def _strip_markup(text):
    """Remove tags and `<!-- ... -->` comments in one left-to-right pass.

    A comment ends at the first `-->` after its `<!--`. Once no `-->` is left in
    the text no later comment can end either, so such starts stay as text and
    are not searched for again. That keeps the time linear in the text length.
    """
    out = []
    pos = 0          # start of the text not yet copied to `out`
    scan = 0         # where the next tag or comment start is searched for
    comments_can_end = True
    while True:
        match = _TAG_OR_COMMENT_START.search(text, scan)
        if match is None:
            break
        if match.group(0) == "<!--":
            end = text.find("-->", match.end()) if comments_can_end else -1
            if end == -1:
                comments_can_end = False
                scan = match.start() + 1   # keep `<!--` as text; a tag may start later
                continue
            out.append(text[pos:match.start()])
            pos = scan = end + 3
        else:
            out.append(text[pos:match.start()])
            pos = scan = match.end()
    out.append(text[pos:])
    return "".join(out)


def clean_headline(text):
    """Plain-text headline (R1.3).

    In this order: tags removed, entities decoded once in a single pass (so
    `&amp;amp;` gives `&amp;`), runs of white space become one space, leading
    and trailing white space removed. Nothing else is changed or cut.
    """
    text = _strip_markup(text)
    text = _ENTITY.sub(_decode_entity, text)
    text = _WHITESPACE_RUN.sub(" ", text)
    return text.strip(WHITESPACE)


# ---------------------------------------------------------------------------
# URL check and normalisation (R9.1, R5.3)

MAX_ITEMS = 20                 # R5.1: items per source
MAX_AGE = timedelta(days=7)    # R5.2

# scheme://authority path ?query #fragment. The character set is checked first
# (see `parse_url`), so `[^/?#]` etc. only ever see printable ASCII.
_URL = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*)://([^/?#]*)([^?#]*)(?:\?[^#]*)?(?:#.*)?\Z")
_HOST = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)*\Z")
_PRINTABLE_ASCII = re.compile(r"^[\x21-\x7E]+\Z")


def parse_url(url):
    """URL text -> `(scheme, host, path)` or None when it is not acceptable.

    Rules (R9.1; the JavaScript version must give the same answers):
    * Leading and trailing white space (the set `WHITESPACE`) is ignored. The
      rest may contain only the printable ASCII characters U+0021 to U+007E:
      white space inside, control characters, non-ASCII characters (so no raw
      IDN host) and everything else are refused. Punycode (`xn--...`) is plain
      ASCII and is treated like any other host name.
    * A backslash anywhere is refused.
    * The scheme must be `http` or `https` (any letter case).
    * The authority may not contain `@` (user information, as in
      `https://svt.se@evil.com/`) and may not have a port, not even the default
      one: the item is dropped. A trailing dot in the host is refused too.
    * The host is lower-cased (ASCII) and must be dot-separated labels of
      `a-z 0-9 -`; this also refuses an empty host, `[`, `%` and `_`.
    * `scheme` and `host` are returned in lower case; `path` is the text
      between the authority and `?` or `#`, unchanged (no percent-decoding).
    """
    if not isinstance(url, str):
        return None
    url = url.strip(WHITESPACE)
    if not _PRINTABLE_ASCII.match(url) or "\\" in url:
        return None
    m = _URL.match(url)
    if not m:
        return None
    scheme, authority, path = m.group(1).lower(), m.group(2).lower(), m.group(3)
    if scheme not in ("http", "https"):
        return None
    if not _HOST.match(authority):  # refuses "@", ":", a trailing dot, empty
        return None
    return scheme, authority, path


def _on_allowed_host(host, allowed_hosts):
    for allowed in allowed_hosts:
        if host == allowed or host.endswith("." + allowed):
            return True
    return False


def check_url(url, allowed_hosts, link_hosts=None):
    """The normalised URL (R5.3) if `url` is usable for a source with these
    `allowedHosts` (R9.1), else None.

    The host is accepted when it equals an allowed host or ends with `.` plus
    one (so `www.svt.se` is accepted and `evilsvt.se` is not). When `link_hosts` is
    given (R9.1 from F6, R16.2), the host must in addition equal one of them exactly
    (compared before `www.` is removed), so a subdomain that is not listed is refused.

    Normalised: lower-case scheme and host, one leading `www.` removed from the
    host, query string and fragment removed, trailing `/` characters removed
    (so `https://svt.se/` is `https://svt.se`). The path keeps its case and is
    not percent-decoded.
    """
    parsed = parse_url(url)
    if parsed is None:
        return None
    scheme, host, path = parsed
    if not _on_allowed_host(host, allowed_hosts):
        return None
    if link_hosts and host not in link_hosts:
        return None
    if host.startswith("www."):
        host = host[4:]
    return scheme + "://" + host + path.rstrip("/")


def item_id(normalised_url):
    """`id` (R5.4): the first 16 hexadecimal characters of the SHA-256 of the
    normalised URL (UTF-8; it is ASCII)."""
    return hashlib.sha256(normalised_url.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Selection

POLITICS = "politics"  # the topic that `select_items` evaluates (R14.7); the build evaluates all topics (R13.3)


def feed_entry(source, topic):
    """The feed entry of `source` for `topic` (R14.2), or None if it has none (R13.7)."""
    for entry in source.get("feeds", ()):
        if entry.get("topic") == topic:
            return entry
    return None


def _uses_keyword_filter(source):
    entry = feed_entry(source, POLITICS)
    if entry is None:
        raise ValueError("source %r has no feed entry for the topic %s" % (source["id"], POLITICS))
    method = entry["method"]
    if method == "keywordFilter":
        return True
    if method == "feed":
        return False  # a dedicated politics feed needs no filter
    raise ValueError("unsupported politics method %r for source %r (raw entries "
                     "carry no categories)" % (method, source["id"]))


def select_items(entries, source, keywords, now):
    """Raw entries of one source -> the list of `NewsItem` to publish.

    `source` is one entry of `sources.json`; `keywords` is a `Keywords` object
    (may be None for a source that does not use `keywordFilter`); `now` is an
    aware datetime. Steps, in this order:

    1. In feed order, each entry: the headline is cleaned (R1.3) and an empty
       one drops the item (R1.4); the keyword filter is applied to the cleaned
       headline and description when the method of the source's `politics` feed entry is
       `keywordFilter` (R4.4); the URL must pass `check_url` (R1.4, R9.1).
    2. Duplicates within the source are removed by normalised URL, the first in
       feed order is kept (R5.3).
    3. `published` is read with `published_utc` (a bad or future time is None).
       An item older than 7 days before `now` is dropped (R5.2); exactly 7 days
       is kept; an item without time is kept.
    4. Sorted newest first by `published`, items without time last; equal times
       by title (compared by Unicode code point), then in feed order (R5.5 for
       one source). At most 20 are kept (R5.1).
    5. Items get exactly the fields of R1.1. The description is dropped here.
    """
    use_keywords = _uses_keyword_filter(source)
    if use_keywords and keywords is None:
        raise ValueError("source %r needs a keyword list" % (source["id"],))
    cutoff = now.astimezone(UTC) - MAX_AGE

    seen = set()
    items = []
    for entry in entries:
        title = clean_headline(entry.title)
        if title == "":
            continue
        if use_keywords and not keywords.matches(entry.title, entry.description):
            continue
        normalised = check_url(entry.link, source["allowedHosts"], source.get("linkHosts"))
        if normalised is None or normalised in seen:
            continue
        seen.add(normalised)
        published = published_utc(entry.time_text, now)
        if published is not None and parse_time(published) < cutoff:
            continue
        items.append(NewsItem(
            id=item_id(normalised),
            sourceId=source["id"],
            sourceName=source["name"],
            title=title,
            url=entry.link.strip(WHITESPACE),
            published=published,
            publishedDisplay=display_time(published),
        ))

    return sort_items(items)[:MAX_ITEMS]


def sort_items(items):
    """Newest `published` first, items without time last; equal times by title
    (Unicode code point), then in the order given (R5.5 for one source)."""
    dated = [i for i in items if i.published is not None]
    undated = [i for i in items if i.published is None]
    # Python's sort is stable, also with reverse=True: equal elements keep their order.
    dated.sort(key=lambda i: i.title)
    dated.sort(key=lambda i: i.published, reverse=True)  # fixed-width UTC text
    undated.sort(key=lambda i: i.title)
    return dated + undated
