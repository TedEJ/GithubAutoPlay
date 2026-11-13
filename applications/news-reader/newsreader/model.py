"""Data shapes shared by the build modules. No I/O."""
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class RawEntry:
    """One RSS item as read from the feed, before any cleaning or selection.

    All fields are plain strings. A missing element gives an empty string.
    `description` is used only for keyword matching later and is never
    published (N1).
    """

    title: str
    link: str
    time_text: str
    description: str


@dataclass(frozen=True)
class NewsItem:
    """One published item: exactly the fields of R1.1 and nothing else.

    No description, content or image (N1). `published` is UTC text or None.
    """

    id: str
    sourceId: str
    sourceName: str
    title: str
    url: str
    published: "str | None"
    publishedDisplay: str

    def as_dict(self):
        """The item as it is written to `news.json` (field order of design 7.4)."""
        return {f.name: getattr(self, f.name) for f in fields(self)}
