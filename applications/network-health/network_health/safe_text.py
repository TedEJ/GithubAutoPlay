"""Text that came over the network is never trusted.

A device chooses its own name, banner and Server header. Before such text is
stored or printed, control characters (including the escape character that
starts terminal commands) are replaced and the length is cut.
"""

from __future__ import annotations


def clean_text(value, max_chars: int = 64) -> str:
    """Printable text of at most max_chars characters; bytes are decoded
    leniently. Control characters and anything that is not printable become a
    space; runs of spaces are made one."""
    if isinstance(value, (bytes, bytearray)):
        value = bytes(value).decode("utf-8", errors="replace")
    text = "".join(ch if ch.isprintable() else " " for ch in str(value))
    text = " ".join(text.split())
    if len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."
    return text
