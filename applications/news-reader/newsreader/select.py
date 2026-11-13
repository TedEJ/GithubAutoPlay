"""Headline cleaning (R1.3). The rest of selection (URL check, duplicates, age,
cap, id) is added in step S7. No I/O.

The cleaning is defined with fixed sets, so the JavaScript version (S9) can
reproduce it exactly. Nothing here depends on Python's `html` module.
"""
import re

# `<` followed by a letter (or `/`, `!--`) starts a tag, so "a < b" stays as it is.
_TAG = re.compile(r"</?[A-Za-z][^<>]*>|<!--.*?-->", re.DOTALL)

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
    code = int(dec) if dec is not None else int(hexa, 16)
    # Valid code points only: not 0, not a surrogate, not above U+10FFFF.
    # &#128; is the plain control character U+0080 (not the euro sign).
    if code == 0 or 0xD800 <= code <= 0xDFFF or code > 0x10FFFF:
        return match.group(0)
    return chr(code)


def clean_headline(text):
    """Plain-text headline (R1.3).

    In this order: tags removed, entities decoded once in a single pass (so
    `&amp;amp;` gives `&amp;`), runs of white space become one space, leading
    and trailing white space removed. Nothing else is changed or cut.
    """
    text = _TAG.sub("", text)
    text = _ENTITY.sub(_decode_entity, text)
    text = _WHITESPACE_RUN.sub(" ", text)
    return text.strip(WHITESPACE)
