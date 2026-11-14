"""The shared keyword lists and keyword matching (R4.3, R4.4, R13.4, R17, design
sections 7.2 and 7.6).

There is one list per topic (`politics-keywords.json`, `nature-keywords.json`,
`ai-keywords.json`), read by this module and by the page (`site/logic.js`), so
neither side has its own copy of the terms. No I/O except `load_keywords` and
`load_topic_keywords`.

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
5b. An include phrase (`include.phrases`) is a hit when its words occur in
   sequence in the lower-case word list at positions none of which was marked by
   an exclude phrase in rule 4. Exclude words do not apply to include phrases.
6. `caseSensitive` terms are exact substrings of the NFC-normalised cleaned text
   (not lowercased, brackets included). `caseSensitiveWords` terms are one whole
   word each, compared with the case kept, in the word list of rule 2 (so
   `AI-regler` has the word `AI`; `AIK`, `FAIR` and `Ai` are other words).
   Exclude phrases and words do not affect either kind.
7. Headline and description are tested separately; one hit in either is a match.
8. `topics_of` (R13.4) applies the rules of the feed entries of one feed URL to
   one item and returns all its topics.
"""
import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from newsreader.select import clean_headline

APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PATH = APP_DIR / "politics-keywords.json"

VERSION = 2
# R13.1: all topic ids in their fixed order; every topic but `all-news` has a keyword file.
TOPIC_ORDER = ("all-news", "politics", "nature", "ai")
KEYWORD_TOPICS = tuple(t for t in TOPIC_ORDER if t != "all-news")


def keyword_file_name(topic):
    """`<topic id>-keywords.json` (R14.1, R17.1)."""
    return topic + "-keywords.json"


class KeywordsError(ValueError):
    """A keyword file is invalid (R6.4: the build must fail)."""


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
    include_phrases: tuple = ()  # tuple of tuples of lower-case words
    case_sensitive_words: frozenset = frozenset()
    topic: str = "politics"

    def _has_hit(self, text):
        text = unicodedata.normalize("NFC", text)
        for term in self.case_sensitive:
            if term in text:
                return True
        if self.case_sensitive_words:
            for word in split_words(text):
                if word in self.case_sensitive_words:
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
        for phrase in self.include_phrases:
            n = len(phrase)
            for i in range(len(words) - n + 1):
                if tuple(words[i:i + n]) == phrase and not any(removed[i:i + n]):
                    return True
        return False

    def matches(self, headline, description=None):
        """True if the item matches this topic's list (R4.4, R17.1).

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


def _phrase_words(phrase, where):
    """A phrase term: two or more words separated by single spaces, nothing else."""
    words = split_words(phrase)
    if len(words) < 2 or " ".join(words) != phrase:
        raise KeywordsError(
            f"{where}: two or more words separated by single spaces, no other characters: {phrase!r}")
    return tuple(words)


def validate_keywords(data, topic=None):
    """Check the shape and rules of the parsed file and return a `Keywords`.

    `topic` is the topic id the file must belong to (R17.5); without it the
    file's own `topic` must be one of the keyword topics. The term lists words,
    phrases, exclude.words and exclude.phrases may be written with capitals (as
    in design 7.2); they are NFC-normalised and lowercased here.

    Raises `KeywordsError` for anything invalid.
    """
    _check_keys(data, ["version", "topic", "include", "exclude"], "file")
    if type(data["version"]) is not int or data["version"] != VERSION:
        raise KeywordsError(f"version must be {VERSION}")
    if topic is not None:
        if data["topic"] != topic:
            raise KeywordsError(f"topic must be {topic!r}")
    elif data["topic"] not in KEYWORD_TOPICS:
        raise KeywordsError(f"topic must be one of {list(KEYWORD_TOPICS)}")
    inc, exc = data["include"], data["exclude"]
    _check_keys(inc, ["words", "phrases", "caseSensitive", "caseSensitiveWords"], "include")
    _check_keys(exc, ["words", "phrases"], "exclude")

    inc_words = _string_list(inc["words"], "include.words", True)
    inc_phrases = _string_list(inc["phrases"], "include.phrases", True)
    case_terms = _string_list(inc["caseSensitive"], "include.caseSensitive", False)
    case_words = _string_list(inc["caseSensitiveWords"], "include.caseSensitiveWords", False)
    exc_words = _string_list(exc["words"], "exclude.words", True)
    exc_phrases = _string_list(exc["phrases"], "exclude.phrases", True)

    if not (inc_words or inc_phrases or case_terms or case_words):
        raise KeywordsError("the include lists are all empty")

    exact, prefixes = [], []
    for term in inc_words:
        body = _single_word(term, "include.words")
        (prefixes if term.endswith("*") else exact).append(body)
    for term in exc_words:
        if term.endswith("*"):
            raise KeywordsError(f"exclude.words: no wildcard allowed: {term!r}")
        _single_word(term, "exclude.words")
    include_phrases = [_phrase_words(p, "include.phrases") for p in inc_phrases]
    phrases = [_phrase_words(p, "exclude.phrases") for p in exc_phrases]
    for term in case_terms:
        if term == term.lower() and term == term.upper():
            raise KeywordsError(f"include.caseSensitive: term has no letters, use words: {term!r}")
    for term in case_words:
        if split_words(term) != [term]:
            raise KeywordsError(
                f"include.caseSensitiveWords: not exactly one word (letters and digits): {term!r}")
        if not any(unicodedata.category(ch)[0] == "L" for ch in term):
            raise KeywordsError(f"include.caseSensitiveWords: term has no letters: {term!r}")

    return Keywords(
        include_exact=frozenset(exact),
        include_prefixes=tuple(prefixes),
        case_sensitive=tuple(case_terms),
        exclude_words=frozenset(exc_words),
        exclude_phrases=tuple(phrases),
        include_phrases=tuple(include_phrases),
        case_sensitive_words=frozenset(case_words),
        topic=data["topic"],
    )


def load_keywords(path=None, topic=None):
    """Read and validate a keyword file (default: `politics-keywords.json` next
    to `sources.json`). With `topic`, the file's `topic` must equal it."""
    path = Path(path) if path is not None else DEFAULT_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (OSError, ValueError) as exc:  # KeywordsError is a ValueError
        raise KeywordsError(f"cannot read {path.name}: {exc}") from exc
    return validate_keywords(data, topic)


def load_topic_keywords(topic, directory=None):
    """The list of one topic, chosen by its id: `<directory>/<topic>-keywords.json`
    (default directory: the application folder). `all-news` has no list."""
    if topic not in KEYWORD_TOPICS:
        raise KeywordsError(f"no keyword list for topic {topic!r}")
    base = Path(directory) if directory is not None else APP_DIR
    return load_keywords(base / keyword_file_name(topic), topic)


def topics_of(headline, description, feeds, keywords_by_topic):
    """All topics of one item (R13.4), in the order of R13.1, without duplicates.

    `headline` and `description` (may be None) are the texts of the item as the
    feed gave them; like `Keywords.matches` this cleans them once (R1.3), so the
    caller does not. `feeds` are the feed entries of the feed URL the item came
    from: dicts with `topic`, `method` and an optional `matchOn` (R14.2).
    `keywords_by_topic` maps a topic id to its `Keywords`.

    A `feed` entry always gives its topic; a `keywordFilter` entry gives it when
    the topic's list matches, and with `matchOn` `title` only the headline is
    read. `categoryFilter` is not supported (raw entries carry no categories).
    """
    found = set()
    for feed in feeds:
        topic, method = feed["topic"], feed["method"]
        if topic not in TOPIC_ORDER:
            raise ValueError("unknown topic %r" % (topic,))
        if method == "feed":
            found.add(topic)
        elif method == "keywordFilter":
            keywords = keywords_by_topic.get(topic)
            if keywords is None:
                raise ValueError("topic %r needs a keyword list" % (topic,))
            text = None if feed.get("matchOn") == "title" else description
            if keywords.matches(headline, text):
                found.add(topic)
        else:
            raise ValueError("unsupported method %r for topic %r" % (method, topic))
    return [t for t in TOPIC_ORDER if t in found]
