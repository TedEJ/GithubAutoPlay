"""Keyword list validation and keyword matching (R4.3, R4.4, R4.5, R6.4, design 7.2)."""
import copy
import json
from pathlib import Path

import pytest

from newsreader.keywords import (
    DEFAULT_PATH, KeywordsError, load_keywords, split_words, validate_keywords,
)

ROOT = Path(__file__).resolve().parent.parent
CASES_FILE = Path(__file__).resolve().parent / "shared-cases.json"
SHARED = json.loads(CASES_FILE.read_text(encoding="utf-8"))
CASES = SHARED["keywords"]
RAW = json.loads((ROOT / "politics-keywords.json").read_text(encoding="utf-8"))

REQUIRED_KINDS = [
    "include-", "party-", "abbr-", "case-", "boundary-", "no-match-",
    "exclude-word-", "exclude-phrase-", "exclude-phrase-overlap", "description-",
    "description-null", "description-empty", "cleaning-", "unicode-",
]


@pytest.fixture(scope="module")
def keywords():
    return load_keywords()


# ---- the keyword file --------------------------------------------------

def test_default_path_is_the_file_in_the_project_folder():
    assert DEFAULT_PATH == ROOT / "politics-keywords.json"


def test_the_file_is_valid_and_loads(keywords):
    assert keywords.include_exact or keywords.include_prefixes


def test_the_file_follows_the_design():
    assert RAW["version"] == 1 and RAW["category"] == "politics-sweden"
    words = RAW["include"]["words"]
    for term in ["riksdag*", "regering*", "statsminister*", "partiledar*", "talman*",
                 "oppositionsledar*", "rosenbad", "budgetproposition*", "riksdagsval*",
                 "socialdemokrat*", "moderat*", "sverigedemokrat*", "centerpartiet",
                 "vänsterpartiet", "kristdemokrat*", "liberalerna", "miljöpartiet"]:
        assert term in words
    assert RAW["include"]["caseSensitive"] == ["(S)", "(M)", "(SD)", "(C)", "(V)", "(KD)", "(L)", "(MP)"]
    assert RAW["exclude"]["words"] == ["moderat", "moderata"]
    assert "tyska regeringen" in RAW["exclude"]["phrases"]
    assert "amerikanska regeringen" in RAW["exclude"]["phrases"]


def test_too_broad_terms_are_not_include_terms():
    for term in ["minister", "minister*", "val", "val*", "parti", "parti*"]:
        assert term not in RAW["include"]["words"]


DESIGN_7_2_SPELLING = {
    "version": 1,
    "category": "politics-sweden",
    "include": {
        "words": ["riksdag*", "regering*", "statsminister*", "partiledar*",
                  "talman*", "oppositionsledar*", "Rosenbad", "budgetproposition*",
                  "riksdagsval*", "Socialdemokrat*", "Moderat*", "Sverigedemokrat*",
                  "Centerpartiet", "Vänsterpartiet", "Kristdemokrat*", "Liberalerna",
                  "Miljöpartiet"],
        "caseSensitive": ["(S)", "(M)", "(SD)", "(C)", "(V)", "(KD)", "(L)", "(MP)"],
    },
    "exclude": {
        "words": ["Moderat", "MODERATA"],
        "phrases": [p.title() for p in RAW["exclude"]["phrases"]],
    },
}


def test_file_spelled_with_capitals_as_in_the_design_loads_the_same():
    assert load_keywords_from(DESIGN_7_2_SPELLING) == load_keywords()


def test_capitalised_file_gives_identical_matching(keywords):
    other = load_keywords_from(DESIGN_7_2_SPELLING)
    for case in CASES:
        inp = case["input"]
        assert other.matches(inp["headline"], inp.get("description")) is \
            keywords.matches(inp["headline"], inp.get("description"))


def test_case_sensitive_terms_keep_their_case():
    data = copy.deepcopy(DESIGN_7_2_SPELLING)
    data["include"]["caseSensitive"] = ["(SD)", "(Xy)"]
    kw = load_keywords_from(data)
    assert kw.case_sensitive == ("(SD)", "(Xy)")
    assert kw.matches("Kalle (Xy) svarar") and not kw.matches("Kalle (xy) svarar")


def test_duplicate_error_names_the_term():
    with pytest.raises(KeywordsError, match="riksdag"):
        validate_keywords(_with(["include", "words"], ["riksdag*", "Riksdag*"]))


def test_duplicate_json_key_error_names_the_key(tmp_path):
    path = tmp_path / "k.json"
    path.write_text('{"version": 1, "version": 1}', encoding="utf-8")
    with pytest.raises(KeywordsError, match="version"):
        load_keywords(path)


def load_keywords_from(data):
    return validate_keywords(data)


def test_file_terms_are_lower_case_except_case_sensitive_ones():
    for term in RAW["include"]["words"] + RAW["exclude"]["words"] + RAW["exclude"]["phrases"]:
        assert term == term.lower()


def _with(path, value):
    data = copy.deepcopy(RAW)
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return data


INVALID = {
    "not-an-object": [],
    "missing-key": {k: v for k, v in RAW.items() if k != "exclude"},
    "extra-key": {**RAW, "note": "x"},
    "wrong-version": {**RAW, "version": 2},
    "version-is-bool": {**RAW, "version": True},
    "wrong-category": {**RAW, "category": "sport"},
    "include-not-object": {**RAW, "include": []},
    "include-extra-key": _with(["include", "phrases"], []),
    "include-missing-key": {**RAW, "include": {"words": ["riksdag*"]}},
    "exclude-extra-key": _with(["exclude", "regex"], []),
    "exclude-missing-key": {**RAW, "exclude": {"words": []}},
    "words-not-list": _with(["include", "words"], "riksdag*"),
    "word-not-string": _with(["include", "words"], ["riksdag*", 5]),
    "word-empty": _with(["include", "words"], ["riksdag*", ""]),
    "word-only-wildcard": _with(["include", "words"], ["*"]),
    "word-surrounding-space": _with(["include", "words"], ["riksdag* "]),
    "word-two-words": _with(["include", "words"], ["ny riksdag"]),
    "word-hyphen": _with(["include", "words"], ["riks-dag"]),
    "word-wildcard-in-the-middle": _with(["include", "words"], ["riks*dag"]),
    "word-double-wildcard": _with(["include", "words"], ["riksdag**"]),
    "word-duplicate": _with(["include", "words"], ["riksdag*", "riksdag*"]),
    "word-capitalised-duplicate": _with(["include", "words"], ["riksdag*", "Riksdag*"]),
    "word-nfd-duplicate": _with(["include", "words"], ["vänsterpartiet", "va\u0308nsterpartiet"]),
    "exclude-word-capitalised-duplicate": _with(["exclude", "words"], ["moderat", "Moderat"]),
    "exclude-phrase-capitalised-duplicate": _with(["exclude", "phrases"], ["tyska regeringen", "Tyska Regeringen"]),
    "case-sensitive-not-nfc": _with(["include", "caseSensitive"], ["(S)", "(A\u030a)"]),
    "case-sensitive-empty-term": _with(["include", "caseSensitive"], ["(S)", ""]),
    "case-sensitive-duplicate": _with(["include", "caseSensitive"], ["(S)", "(S)"]),
    "case-sensitive-without-letters": _with(["include", "caseSensitive"], ["()"]),
    "case-sensitive-not-list": _with(["include", "caseSensitive"], "(S)"),
    "include-all-empty": {**RAW, "include": {"words": [], "caseSensitive": []}},
    "exclude-word-empty": _with(["exclude", "words"], [""]),
    "exclude-word-wildcard": _with(["exclude", "words"], ["moderat*"]),
    "exclude-word-duplicate": _with(["exclude", "words"], ["moderat", "moderat"]),
    "exclude-phrase-empty": _with(["exclude", "phrases"], [""]),
    "exclude-phrase-one-word": _with(["exclude", "phrases"], ["regeringen"]),
    "exclude-phrase-double-space": _with(["exclude", "phrases"], ["tyska  regeringen"]),
    "exclude-phrase-punctuation": _with(["exclude", "phrases"], ["tyska, regeringen"]),
    "exclude-phrase-duplicate": _with(["exclude", "phrases"], ["tyska regeringen", "tyska regeringen"]),
    "exclude-phrase-not-string": _with(["exclude", "phrases"], [["tyska", "regeringen"]]),
}


@pytest.mark.parametrize("name", sorted(INVALID))
def test_invalid_file_is_an_error(name):
    with pytest.raises(KeywordsError):
        validate_keywords(INVALID[name])


def test_empty_exclude_lists_are_allowed():
    data = _with(["exclude", "words"], [])
    data["exclude"]["phrases"] = []
    validate_keywords(data)


def test_load_rejects_broken_json(tmp_path):
    path = tmp_path / "k.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(KeywordsError):
        load_keywords(path)


def test_load_rejects_duplicate_keys(tmp_path):
    path = tmp_path / "k.json"
    text = json.dumps(RAW).replace('"version": 1', '"version": 1, "version": 1', 1)
    path.write_text(text, encoding="utf-8")
    with pytest.raises(KeywordsError):
        load_keywords(path)


def test_load_rejects_missing_file(tmp_path):
    with pytest.raises(KeywordsError):
        load_keywords(tmp_path / "missing.json")


def test_load_reads_a_valid_copy(tmp_path):
    path = tmp_path / "k.json"
    path.write_text(json.dumps(RAW), encoding="utf-8")
    assert load_keywords(path) == load_keywords()


# ---- word splitting ------------------------------------------------------

def test_split_words_letters_and_digits_only():
    assert split_words("Riksdagen, år 2026: åäö-ÅÄÖ_x") == ["Riksdagen", "år", "2026", "åäö", "ÅÄÖ", "x"]
    assert split_words("") == []
    assert split_words("(( ))") == []


def test_split_words_normalises_to_nfc():
    assert split_words("Miljöpartiet") == ["Miljöpartiet"]


# ---- shared cases ----------------------------------------------------------

def test_shared_keyword_cases_have_id_input_expected():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))
    for case in CASES:
        assert set(case) == {"id", "input", "expected"}
        assert set(case["input"]) in ({"headline"}, {"headline", "description"})
        assert isinstance(case["input"]["headline"], str)
        assert isinstance(case["input"].get("description", ""), (str, type(None)))
        assert set(case["expected"]) == {"match"}
        assert isinstance(case["expected"]["match"], bool)


def test_shared_keyword_cases_cover_the_rules():
    ids = " ".join(c["id"] for c in CASES)
    for kind in REQUIRED_KINDS:
        assert kind in ids, kind
    assert any(c["expected"]["match"] for c in CASES)
    assert any(not c["expected"]["match"] for c in CASES)
    assert any("description" not in c["input"] for c in CASES)
    assert any(c["input"].get("description", 0) is None for c in CASES)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_shared_keyword_case(keywords, case):
    inp = case["input"]
    assert keywords.matches(inp["headline"], inp.get("description")) is case["expected"]["match"]


# ---- direct tests ------------------------------------------------------------

def test_description_argument_is_optional(keywords):
    assert keywords.matches("Riksdagen röstar") is True
    assert keywords.matches("Vädret") is False


def test_matches_returns_only_a_bool(keywords):
    assert keywords.matches("Ny rapport", "Debatt i riksdagen") is True


def test_every_party_abbreviation_and_name_matches(keywords):
    for abbr in RAW["include"]["caseSensitive"]:
        assert keywords.matches(f"Kalle {abbr} svarar")
    for term in RAW["include"]["words"]:
        word = term.rstrip("*")
        if word in RAW["exclude"]["words"]:
            word += "erna"  # the bare word is an exclude word (moderat)
        assert keywords.matches(word)
        assert keywords.matches(word.upper())


def test_every_exclude_phrase_alone_does_not_match(keywords):
    for phrase in RAW["exclude"]["phrases"]:
        assert not keywords.matches(f"Idag: {phrase} sänker skatten")
        assert keywords.matches(f"{phrase} och riksdagen")


def test_exclusion_never_drops_a_whole_item(keywords):
    assert keywords.matches("Tyska regeringen och moderat tillväxt men Sverigedemokraterna svarar")
