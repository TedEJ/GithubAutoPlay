"""Data shapes shared by the build modules. No I/O."""
from dataclasses import dataclass


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
