"""The shared keyword list and keyword matching (R4.3, R4.4, design section 7.2).

`politics-keywords.json` is read by this module (and later by the page, S9), so
neither side has its own copy of the terms. No I/O except `load_keywords`.

The matching is defined with explicit rules so that the JavaScript version (S9)
gives the same result for every case in `tests/shared-cases.json`:

1. The cleaned text (`clean_headline`) is Unicode NFC-normalised.
2. It is split into words: maximal runs of Unicode letters (general category
   starting with L) and decimal digits (category Nd). Python checks
   `unicodedata.category`; JavaScript uses `[\\p{L}\\p{Nd}]+` with the `u` flag.
   Do not use `str.isalpha`, `str.isalnum` or `\\w` (they differ from that set).
3. Each word is lowercased with `str.lower` (JavaScript `toLowerCase`).
4. Exclude phrases: every place where a phrase's words occur in sequence is
   marked, and all marked words are taken out. All phrases are marked on the
   original word list first and removed together, so overlapping phrases and
   phrases next to each other behave the same everywhere.
5. A remaining word is a hit if it is not an exclude word and an include term
   matches it: a term ending in `*` matches every word that starts with the term
   without the `*`; any other term matches the whole word only.
6. `caseSensitive` terms are exact substrings of the NFC-normalised cleaned text
   (not lowercased, brackets included). Exclude phrases and words do not affect
   them.
7. Headline and description are tested separately; one hit in either is a match.
"""
import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from newsreader.select import clean_headline

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "politics-keywords.json"

CATEGORY = "politics-sweden"
VERSION = 1


class KeywordsError(ValueError):
    """politics-keywords.json is invalid (R6.4: the build must fail)."""


def split_words(text):
    """Words of `text` (rule 2). The text is NFC-normalised first; case is kept."""
    text = unicodedata.normalize("NFC", text)
    words = []
    current = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat[0] == "L" or cat == "Nd":
            current.append(ch)
        elif current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))
    return words


def _lower_words(text):
    return [w.lower() for w in split_words(text)]


@dataclass(frozen=True)
class Keywords:
    """A validated keyword list, ready for matching."""

    include_exact: frozenset
    include_prefixes: tuple
    case_sensitive: tuple
    exclude_words: frozenset
    exclude_phrases: tuple  # tuple of tuples of words

    def _has_hit(self, text):
        text = unicodedata.normalize("NFC", text)
        for term in self.case_sensitive:
            if term in text:
                return True
        words = _lower_words(text)
        removed = [False] * len(words)
        for phrase in self.exclude_phrases:
            n = len(phrase)
            for i in range(len(words) - n + 1):
                if tuple(words[i:i + n]) == phrase:
                    for j in range(i, i + n):
                        removed[j] = True
        for word, gone in zip(words, removed):
            if gone or word in self.exclude_words:
                continue
            if word in self.include_exact:
                return True
            for prefix in self.include_prefixes:
                if word.startswith(prefix):
                    return True
        return False

    def matches(self, headline, description=None):
        """True if the item is about Swedish politics (R4.4).

        Both texts are cleaned with `clean_headline` first. A missing (`None`)
        or empty description is ignored. The description is only read here; it
        is never returned or stored.
        """
        for text in (headline, description):
            if text is None or text == "":
                continue
            if self._has_hit(clean_headline(text)):
                return True
        return False


def _reject_duplicate_keys(pairs):
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise KeywordsError(f"duplicate key in object: {key!r}")
        seen.add(key)
    return dict(pairs)


def _string_list(value, where, lowercase):
    """Check a list of terms and return it.

    `lowercase=True` (words, exclude words, exclude phrases): capitals are
    accepted; each term is NFC-normalised and then lowercased, and duplicates are
    found after that. `lowercase=False` (caseSensitive): terms must already be
    NFC and are kept exactly as written.
    """
    if not isinstance(value, list):
        raise KeywordsError(f"{where} must be a list")
    result = []
    for item in value:
        if not isinstance(item, str):
            raise KeywordsError(f"{where} must hold only strings")
        if item == "" or item != item.strip():
            raise KeywordsError(f"{where}: empty term or term with surrounding white space: {item!r}")
        nfc = unicodedata.normalize("NFC", item)
        if lowercase:
            item = nfc.lower()
        elif nfc != item:
            raise KeywordsError(f"{where}: term is not NFC-normalised: {item!r}")
        result.append(item)
    seen = set()
    for item in result:
        if item in seen:
            raise KeywordsError(f"{where}: duplicate term (after lowercasing): {item!r}")
        seen.add(item)
    return result


def _check_keys(obj, allowed, where):
    if not isinstance(obj, dict):
        raise KeywordsError(f"{where} must be an object")
    if set(obj) != set(allowed):
        raise KeywordsError(f"{where} must have exactly the keys {sorted(allowed)}, got {sorted(obj)}")


def _single_word(term, where):
    """A `words` term: one lower-case word, optionally ending in one `*`."""
    body = term[:-1] if term.endswith("*") else term
    if body == "" or split_words(body) != [body]:
        raise KeywordsError(f"{where}: not a single word (letters and digits, optional trailing *): {term!r}")
    return body


def validate_keywords(data):
    """Check the shape and rules of the parsed file and return a `Keywords`.

    The term lists words, exclude.words and exclude.phrases may be written with
    capitals (as in design 7.2); they are NFC-normalised and lowercased here.

    Raises `KeywordsError` for anything invalid.
    """
    _check_keys(data, ["version", "category", "include", "exclude"], "file")
    if type(data["version"]) is not int or data["version"] != VERSION:
        raise KeywordsError(f"version must be {VERSION}")
    if data["category"] != CATEGORY:
        raise KeywordsError(f"category must be {CATEGORY!r}")
    inc, exc = data["include"], data["exclude"]
    _check_keys(inc, ["words", "caseSensitive"], "include")
    _check_keys(exc, ["words", "phrases"], "exclude")

    inc_words = _string_list(inc["words"], "include.words", True)
    case_terms = _string_list(inc["caseSensitive"], "include.caseSensitive", False)
    exc_words = _string_list(exc["words"], "exclude.words", True)
    exc_phrases = _string_list(exc["phrases"], "exclude.phrases", True)

    if not inc_words and not case_terms:
        raise KeywordsError("the include lists are both empty")

    exact, prefixes = [], []
    for term in inc_words:
        body = _single_word(term, "include.words")
        (prefixes if term.endswith("*") else exact).append(body)
    for term in exc_words:
        if term.endswith("*"):
            raise KeywordsError(f"exclude.words: no wildcard allowed: {term!r}")
        _single_word(term, "exclude.words")
    phrases = []
    for phrase in exc_phrases:
        words = split_words(phrase)
        if len(words) < 2 or " ".join(words) != phrase:
            raise KeywordsError(
                f"exclude.phrases: two or more words separated by single spaces, no other characters: {phrase!r}")
        phrases.append(tuple(words))
    for term in case_terms:
        if term == term.lower() and term == term.upper():
            raise KeywordsError(f"include.caseSensitive: term has no letters, use words: {term!r}")

    return Keywords(
        include_exact=frozenset(exact),
        include_prefixes=tuple(prefixes),
        case_sensitive=tuple(case_terms),
        exclude_words=frozenset(exc_words),
        exclude_phrases=tuple(phrases),
    )


def load_keywords(path=None):
    """Read and validate the keyword file (default: the one next to `sources.json`)."""
    path = Path(path) if path is not None else DEFAULT_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (OSError, ValueError) as exc:  # KeywordsError is a ValueError
        raise KeywordsError(f"cannot read {path.name}: {exc}") from exc
    return validate_keywords(data)
