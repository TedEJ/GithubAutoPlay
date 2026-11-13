"""RSS 2.0 bytes -> raw entries (R11.1, R9.4, R10.1). No network, no cleaning."""
from xml.parsers import expat

from .model import RawEntry

# R9.4: a response larger than this is refused (2 MiB).
MAX_RESPONSE_BYTES = 2 * 1024 * 1024

# R10.1: the only encodings accepted (compared in lower case).
_ALLOWED_ENCODINGS = ("utf-8", "iso-8859-1")

_FIELDS = {"title": "title", "link": "link", "pubDate": "time_text", "description": "description"}


class FeedError(Exception):
    """The document is not a usable RSS 2.0 feed. The build treats it as a failed fetch."""


def _refuse_entity_declaration(*_args):
    raise FeedError("entity declarations are not allowed")


def _check_declared_encoding(version, encoding, standalone):
    if encoding is not None and encoding.lower() not in _ALLOWED_ENCODINGS:
        raise FeedError("encoding %r is not accepted (only UTF-8 and ISO-8859-1)" % encoding)


def _looks_like_utf16_or_utf32(data):
    """True for a UTF-16 byte order mark, or a document whose first characters
    are ASCII spread over several bytes (null bytes at the start: UTF-16/32
    without a mark). A UTF-8 byte order mark is fine."""
    return data.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in data[:4]


class _Reader:
    """Collects the four fields of every <rss><channel><item> from expat events.

    Namespaced elements (the namespace separator is `}`) never match a field
    name, and the root only counts as <rss> when it has no namespace. Of a
    repeated field the first one is used. Text of nested elements is included.
    """

    def __init__(self):
        self.stack = []
        self.item = None
        self.field = None  # (name, depth) while inside a wanted field
        self.parts = []
        self.entries = []

    def start(self, name, attrs):
        if not self.stack and name != "rss":
            raise FeedError("root element is not <rss>")
        self.stack.append(name)
        depth = len(self.stack)
        if self.field is not None:
            return
        if depth == 3 and name == "item" and self.stack[:2] == ["rss", "channel"]:
            self.item = {}
        elif depth == 4 and self.item is not None and name in _FIELDS:
            self.field = (name, depth)
            self.parts = []

    def chars(self, data):
        if self.field is not None:
            self.parts.append(data)

    def end(self, name):
        depth = len(self.stack)
        if self.field == (name, depth):
            self.item.setdefault(_FIELDS[name], "".join(self.parts))
            self.field = None
        elif depth == 3 and name == "item" and self.item is not None:
            item, self.item = self.item, None
            title = item.get("title", "")
            link = item.get("link", "").strip()
            time_text = item.get("time_text", "").strip()
            description = item.get("description", "")
            if title.strip() or link or time_text or description.strip():
                self.entries.append(RawEntry(title, link, time_text, description))
        self.stack.pop()


def parse_rss(data):
    """Parse an RSS 2.0 document given as bytes and return a list of RawEntry.

    Encoding (R10.1): only UTF-8 (the default) and ISO-8859-1 are accepted.
    The XML parser decodes by the XML declaration, so the input must be the
    undecoded response body. UTF-16, UTF-32 (with or without a declaration)
    and any other declared encoding are a FeedError.

    Safety (R9.4): data larger than MAX_RESPONSE_BYTES is refused (checked
    first), and a document that declares any entity (the way to reach external
    files or to inflate a document) is refused by the XML parser itself. No
    external entity is ever loaded.

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
    if len(data) > MAX_RESPONSE_BYTES:
        raise FeedError("response larger than 2 MB")
    if not data.strip():
        raise FeedError("empty response")
    data = bytes(data)
    if _looks_like_utf16_or_utf32(data):
        raise FeedError("encoding is not accepted (only UTF-8 and ISO-8859-1)")

    reader = _Reader()
    parser = expat.ParserCreate(namespace_separator="}")
    parser.StartElementHandler = reader.start
    parser.EndElementHandler = reader.end
    parser.CharacterDataHandler = reader.chars
    parser.XmlDeclHandler = _check_declared_encoding
    # Any entity declaration, including parameter entities, is refused. No
    # ExternalEntityRefHandler is set, so nothing external is ever loaded.
    parser.EntityDeclHandler = _refuse_entity_declaration
    try:
        parser.Parse(data, True)
    except expat.ExpatError as exc:
        raise FeedError("not well-formed XML: %s" % exc) from exc
    return reader.entries
