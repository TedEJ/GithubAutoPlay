"""RSS 2.0 bytes -> raw entries (R11.1, R9.4, R10.1). No network, no cleaning."""
import xml.etree.ElementTree as ET

from .model import RawEntry

# R9.4: a response larger than this is refused (2 MiB).
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class FeedError(Exception):
    """The document is not a usable RSS 2.0 feed. The build treats it as a failed fetch."""


def _text(item, name):
    """Text of the direct, un-namespaced child `name`, or "" when missing.

    Text inside child elements is included, so a title with stray markup
    elements does not lose words. Surrounding white space is kept for the
    cleaning step, except for the link, which the caller strips.
    """
    child = item.find(name)
    if child is None:
        return ""
    return "".join(child.itertext())


def parse_rss(data):
    """Parse an RSS 2.0 document given as bytes and return a list of RawEntry.

    Encoding (R10.1): the XML parser decodes by the XML declaration
    (UTF-8 by default, ISO-8859-1 when declared). The input must therefore be
    the undecoded response body.

    Safety (R9.4): data larger than MAX_RESPONSE_BYTES is refused, and a
    document that declares entities (the way to reach external files or to
    inflate a document) is refused. The parser never loads external entities.

    Items (R11.1 and section 8 of the design): only `title`, `link`, `pubDate`
    and `description` are read; `guid`, images and categories are ignored.
    An item without any of the four is skipped. Other items are kept as they
    are, with "" for what is missing; dropping items with an empty title or
    without a usable link is the job of the selection step (R1.4, R9.1).
    Raises FeedError if the data is empty, too large, not well-formed XML, or
    its root element is not <rss>.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("parse_rss needs the undecoded bytes of the response")
    if not data.strip():
        raise FeedError("empty response")
    if len(data) > MAX_RESPONSE_BYTES:
        raise FeedError("response larger than 2 MB")
    if b"<!ENTITY" in data:
        raise FeedError("entity declarations are not allowed")
    try:
        root = ET.fromstring(bytes(data))
    except (ET.ParseError, LookupError, ValueError) as exc:
        raise FeedError("not well-formed XML: %s" % exc) from exc
    if root.tag != "rss":
        raise FeedError("root element is not <rss>")

    entries = []
    for channel in root.findall("channel"):
        for item in channel.findall("item"):
            title = _text(item, "title")
            link = _text(item, "link").strip()
            time_text = _text(item, "pubDate").strip()
            description = _text(item, "description")
            if not (title.strip() or link or time_text or description.strip()):
                continue
            entries.append(RawEntry(title, link, time_text, description))
    return entries
