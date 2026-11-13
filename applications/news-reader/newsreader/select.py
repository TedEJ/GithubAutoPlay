"""Headline cleaning (R1.3). The rest of selection (URL check, duplicates, age,
cap, id) is added in step S7. No I/O."""
import html
import re

# `<` followed by a letter (or `/`, `!--`) starts a tag, so "a < b" stays as it is.
_TAG = re.compile(r"</?[A-Za-z][^<>]*>|<!--.*?-->", re.DOTALL)
# White space is ASCII white space only, so Python and JavaScript agree.
# A no-break space (U+00A0, also what &nbsp; decodes to) is not collapsed.
_WHITESPACE = re.compile(r"[ \t\n\r\f\v]+")
_STRIP = " \t\n\r\f\v"


def clean_headline(text):
    """Plain-text headline (R1.3).

    In this order: tags removed, entities decoded once (so `&amp;amp;` gives
    `&amp;`), runs of white space become one space, trimmed. Nothing else is
    changed or cut.
    """
    text = _TAG.sub("", text)
    text = html.unescape(text)
    text = _WHITESPACE.sub(" ", text)
    return text.strip(_STRIP)
