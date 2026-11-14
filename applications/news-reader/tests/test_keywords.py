"""Keyword lists per topic: validation, matching and `topics_of` (R4.3 to R4.5, R6.4, R13.4, R17, design 7.2 and 7.6)."""
import copy
import json
from pathlib import Path

import pytest

from newsreader.keywords import (
    DEFAULT_PATH, KEYWORD_TOPICS, TOPIC_ORDER, KeywordsError, keyword_file_name,
    load_keywords, load_topic_keywords, split_words, topics_of, validate_keywords,
)

ROOT = Path(__file__).resolve().parent.parent
CASES_FILE = Path(__file__).resolve().parent / "shared-cases.json"
SHARED = json.loads(CASES_FILE.read_text(encoding="utf-8"))
CASES = SHARED["keywords"]
TOPIC_CASES = SHARED["topics"]
RAW = json.loads((ROOT / "politics-keywords.json").read_text(encoding="utf-8"))

REQUIRED_KINDS = [
    "include-", "party-", "abbr-", "case-", "boundary-", "no-match-",
    "exclude-word-", "exclude-phrase-", "exclude-phrase-overlap", "description-",
    "description-null", "description-empty", "cleaning-", "unicode-",
]


@pytest.fixture(scope="module")
def keywords():
    return load_keywords()


@pytest.fixture(scope="module")
def all_keywords():
    return {topic: load_topic_keywords(topic) for topic in KEYWORD_TOPICS}


# ---- the keyword file --------------------------------------------------

def test_default_path_is_the_file_in_the_project_folder():
    assert DEFAULT_PATH == ROOT / "politics-keywords.json"


def test_the_file_is_valid_and_loads(keywords):
    assert keywords.include_exact or keywords.include_prefixes


def test_the_file_follows_the_design():
    assert RAW["version"] == 2 and RAW["topic"] == "politics"
    assert "category" not in RAW
    assert RAW["include"]["phrases"] == [] and RAW["include"]["caseSensitiveWords"] == []
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
    "version": 2,
    "topic": "politics",
    "include": {
        "words": ["riksdag*", "regering*", "statsminister*", "partiledar*",
                  "talman*", "oppositionsledar*", "Rosenbad", "budgetproposition*",
                  "riksdagsval*", "Socialdemokrat*", "Moderat*", "Sverigedemokrat*",
                  "Centerpartiet", "Vänsterpartiet", "Kristdemokrat*", "Liberalerna",
                  "Miljöpartiet"],
        "phrases": [],
        "caseSensitive": ["(S)", "(M)", "(SD)", "(C)", "(V)", "(KD)", "(L)", "(MP)"],
        "caseSensitiveWords": [],
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
    path.write_text('{"version": 2, "version": 2}', encoding="utf-8")
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
    "wrong-version": {**RAW, "version": 1},
    "version-is-bool": {**RAW, "version": True},
    "version-1-with-category": {"version": 1, "category": "politics-sweden",
                                "include": {"words": ["riksdag*"], "caseSensitive": []},
                                "exclude": {"words": [], "phrases": []}},
    "category-instead-of-topic": {**{k: v for k, v in RAW.items() if k != "topic"}, "category": "politics-sweden"},
    "unknown-topic": {**RAW, "topic": "sport"},
    "all-news-has-no-list": {**RAW, "topic": "all-news"},
    "include-not-object": {**RAW, "include": []},
    "include-extra-key": _with(["include", "regex"], []),
    "include-missing-key": {**RAW, "include": {"words": ["riksdag*"], "caseSensitive": []}},
    "include-missing-phrases": {**RAW, "include": {k: v for k, v in RAW["include"].items() if k != "phrases"}},
    "include-missing-case-sensitive-words": {
        **RAW, "include": {k: v for k, v in RAW["include"].items() if k != "caseSensitiveWords"}},
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
    "include-all-empty": {**RAW, "include": {"words": [], "phrases": [], "caseSensitive": [],
                                             "caseSensitiveWords": []}},
    # include.phrases (R17.3)
    "phrase-not-list": _with(["include", "phrases"], "ny riksdag"),
    "phrase-not-string": _with(["include", "phrases"], [["ny", "riksdag"]]),
    "phrase-empty": _with(["include", "phrases"], [""]),
    "phrase-one-word": _with(["include", "phrases"], ["riksdag"]),
    "phrase-wildcard": _with(["include", "phrases"], ["ny riksdag*"]),
    "phrase-double-space": _with(["include", "phrases"], ["ny  riksdag"]),
    "phrase-punctuation": _with(["include", "phrases"], ["ny, riksdag"]),
    "phrase-surrounding-space": _with(["include", "phrases"], ["ny riksdag "]),
    "phrase-duplicate": _with(["include", "phrases"], ["ny riksdag", "ny riksdag"]),
    "phrase-capitalised-duplicate": _with(["include", "phrases"], ["ny riksdag", "Ny Riksdag"]),
    # include.caseSensitiveWords (R17.3)
    "csw-not-list": _with(["include", "caseSensitiveWords"], "AI"),
    "csw-not-string": _with(["include", "caseSensitiveWords"], [5]),
    "csw-empty": _with(["include", "caseSensitiveWords"], [""]),
    "csw-two-words": _with(["include", "caseSensitiveWords"], ["AI Sweden"]),
    "csw-hyphen": _with(["include", "caseSensitiveWords"], ["AI-lag"]),
    "csw-wildcard": _with(["include", "caseSensitiveWords"], ["AI*"]),
    "csw-no-letter": _with(["include", "caseSensitiveWords"], ["2026"]),
    "csw-surrounding-space": _with(["include", "caseSensitiveWords"], [" AI"]),
    "csw-not-nfc": _with(["include", "caseSensitiveWords"], ["A\u030a"]),
    "csw-duplicate": _with(["include", "caseSensitiveWords"], ["AI", "AI"]),
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
    text = json.dumps(RAW).replace('"version": 2', '"version": 2, "version": 2', 1)
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
        assert set(case["input"]) in ({"headline"}, {"headline", "description"},
                                      {"topic", "headline"}, {"topic", "headline", "description"})
        assert case["input"].get("topic", "politics") in KEYWORD_TOPICS
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
def test_shared_keyword_case(all_keywords, case):
    inp = case["input"]
    keywords = all_keywords[inp.get("topic", "politics")]  # a missing topic means politics (R17.4)
    assert keywords.matches(inp["headline"], inp.get("description")) is case["expected"]["match"]


def test_every_topic_has_cases_of_every_kind():
    for topic in KEYWORD_TOPICS:
        mine = [c for c in CASES if c["input"].get("topic", "politics") == topic]
        assert any(c["expected"]["match"] for c in mine), topic
        assert any(not c["expected"]["match"] for c in mine), topic
        assert any("description" in c["input"] for c in mine), topic
    nature = [c["id"] for c in CASES if c["input"].get("topic") == "nature"]
    ai = [c["id"] for c in CASES if c["input"].get("topic") == "ai"]
    for kind in ["exclude-phrase", "no-match-", "description-", "cleaning-", "unicode-", "phrase-", "include-"]:
        assert any(kind in i for i in nature), kind
    for kind in ["case-sensitive-word", "no-match-", "description-", "cleaning-", "unicode-", "phrase-", "word-"]:
        assert any(kind in i for i in ai), kind
    assert any(i.startswith("ai-no-match-AIK") for i in ai)
    assert any("Ai-Weiwei" in c["input"]["headline"] or "Ai Weiwei" in c["input"]["headline"]
               for c in CASES if c["input"].get("topic") == "ai")


# ---- the topic files (R14.1, R17.1, R17.2, R17.5) ----------------------------------

def test_file_names_follow_the_topic_ids():
    assert [keyword_file_name(t) for t in KEYWORD_TOPICS] == [
        "politics-keywords.json", "nature-keywords.json", "ai-keywords.json"]
    assert TOPIC_ORDER == ("all-news", "politics", "nature", "ai")


@pytest.mark.parametrize("topic", KEYWORD_TOPICS)
def test_each_topic_file_loads_by_name_and_has_its_own_topic(topic):
    kw = load_topic_keywords(topic)
    assert kw.topic == topic
    raw = json.loads((ROOT / keyword_file_name(topic)).read_text(encoding="utf-8"))
    assert raw["version"] == 2 and raw["topic"] == topic
    assert set(raw) == {"version", "topic", "include", "exclude"}
    assert set(raw["include"]) == {"words", "phrases", "caseSensitive", "caseSensitiveWords"}
    assert set(raw["exclude"]) == {"words", "phrases"}


def test_load_topic_keywords_refuses_all_news_and_unknown_topics():
    for topic in ["all-news", "sport", "", "../politics"]:
        with pytest.raises(KeywordsError):
            load_topic_keywords(topic)


def test_load_topic_keywords_reads_another_folder(tmp_path):
    (tmp_path / "ai-keywords.json").write_text(
        (ROOT / "ai-keywords.json").read_text(encoding="utf-8"), encoding="utf-8")
    assert load_topic_keywords("ai", tmp_path) == load_topic_keywords("ai")
    with pytest.raises(KeywordsError):
        load_topic_keywords("nature", tmp_path)  # file missing in that folder


def test_a_file_must_have_the_topic_it_is_loaded_for(tmp_path):
    path = tmp_path / "x.json"
    path.write_text((ROOT / "ai-keywords.json").read_text(encoding="utf-8"), encoding="utf-8")
    assert load_keywords(path, "ai").topic == "ai"
    with pytest.raises(KeywordsError, match="topic"):
        load_keywords(path, "nature")


def test_ai_list_has_swedish_and_english_terms_and_the_case_sensitive_word_ai():
    raw = json.loads((ROOT / "ai-keywords.json").read_text(encoding="utf-8"))
    assert "AI" in raw["include"]["caseSensitiveWords"]
    phrases = raw["include"]["phrases"]
    for term in ["artificiell intelligens", "artificial intelligence", "machine learning", "language model"]:
        assert term in phrases
    words = raw["include"]["words"]
    for term in ["chatgpt", "openai", "språkmodell*", "maskininlärning*"]:
        assert term in words
    assert "KI" not in raw["include"]["caseSensitiveWords"] and "ki" not in words  # K16
    assert "ai" not in words and "ai*" not in words  # a lower-case match would hit many words


def test_nature_list_uses_no_broad_prefix():
    raw = json.loads((ROOT / "nature-keywords.json").read_text(encoding="utf-8"))
    for term in ["natur*", "djur*", "miljö*", "klimat*", "storm*", "väder*"]:
        assert term not in raw["include"]["words"]  # K15


@pytest.mark.parametrize("topic", KEYWORD_TOPICS)
def test_file_terms_are_lower_case_except_case_sensitive_ones_in_every_file(topic):
    raw = json.loads((ROOT / keyword_file_name(topic)).read_text(encoding="utf-8"))
    for term in (raw["include"]["words"] + raw["include"]["phrases"]
                 + raw["exclude"]["words"] + raw["exclude"]["phrases"]):
        assert term == term.lower()


# ---- the new term kinds (R17.3) ---------------------------------------------------

def _custom(**include):
    data = {"version": 2, "topic": "ai",
            "include": {"words": [], "phrases": [], "caseSensitive": [], "caseSensitiveWords": [], **include},
            "exclude": {"words": [], "phrases": []}}
    return data


def test_only_phrases_or_only_case_sensitive_words_is_a_valid_file():
    assert validate_keywords(_custom(phrases=["ny riksdag"]))
    assert validate_keywords(_custom(caseSensitiveWords=["AI"]))


def test_include_phrase_needs_the_words_in_sequence():
    kw = validate_keywords(_custom(phrases=["Machine Learning"]))
    assert kw.matches("Machine learning är kul") and kw.matches("MACHINE LEARNING")
    assert not kw.matches("Learning machine") and not kw.matches("Machine and learning")
    assert not kw.matches("Machines learning")  # whole words only


def test_exclude_words_do_not_apply_to_include_phrases():
    data = _custom(phrases=["machine learning"])
    data["exclude"]["words"] = ["machine", "learning"]
    assert validate_keywords(data).matches("Machine learning")


def test_exclude_phrase_marking_blocks_an_include_phrase_at_those_positions():
    data = _custom(phrases=["machine learning"], words=["zzz"])
    data["exclude"]["phrases"] = ["learning conference"]
    kw = validate_keywords(data)
    assert not kw.matches("machine learning conference")      # "learning" is marked
    assert kw.matches("machine learning conference and machine learning")  # the second one is free
    assert kw.matches("machine learning")


def test_exclude_phrase_does_not_touch_case_sensitive_words_or_terms():
    data = _custom(caseSensitiveWords=["AI"], caseSensitive=["(AI)"])
    data["exclude"]["phrases"] = ["ai regler"]
    data["exclude"]["words"] = ["ai"]
    kw = validate_keywords(data)
    assert kw.matches("AI regler") and kw.matches("Nya (AI) regler")


def test_case_sensitive_word_is_a_whole_word_with_exact_case():
    kw = validate_keywords(_custom(caseSensitiveWords=["AI", "Åre"]))
    for text in ["AI", "Ny AI-lag", "AI2024 är fel", "(AI)", "Åre skidar"]:
        assert kw.matches(text) is (text != "AI2024 är fel"), text
    for text in ["AIK", "FAIR", "Ai Weiwei", "ai", "aI", "AI2", "MAIL", "åre"]:
        assert not kw.matches(text), text


def test_case_sensitive_word_is_compared_on_the_nfc_text():
    kw = validate_keywords(_custom(caseSensitiveWords=["\u00c5re"]))
    assert kw.matches("A\u030are skidar") and not kw.matches("a\u030are skidar")


# ---- topics_of (R13.4) ----------------------------------------------------------------

def test_shared_topic_cases_have_id_input_expected():
    ids = [c["id"] for c in TOPIC_CASES]
    assert len(ids) == len(set(ids))
    for case in TOPIC_CASES:
        assert set(case) == {"id", "input", "expected"}
        assert set(case["input"]) in ({"headline", "feeds"}, {"headline", "description", "feeds"})
        assert isinstance(case["expected"], list)
        assert all(t in TOPIC_ORDER for t in case["expected"])
        assert case["expected"] == [t for t in TOPIC_ORDER if t in case["expected"]]
        assert all(set(f) in ({"topic", "method"}, {"topic", "method", "matchOn"}) for f in case["input"]["feeds"])


def test_shared_topic_cases_cover_the_design_list():
    ids = " ".join(c["id"] for c in TOPIC_CASES)
    for kind in ["several", "one-topic", "all-news-only", "match-on-title", "description", "order", "not-offered"]:
        assert kind in ids, kind
    assert any(len(c["expected"]) >= 3 for c in TOPIC_CASES)
    assert any(c["expected"] == ["all-news"] for c in TOPIC_CASES)


@pytest.mark.parametrize("case", TOPIC_CASES, ids=[c["id"] for c in TOPIC_CASES])
def test_shared_topic_case(all_keywords, case):
    inp = case["input"]
    assert topics_of(inp["headline"], inp.get("description"), inp["feeds"], all_keywords) == case["expected"]


def test_topics_of_matches_the_single_topic_matching(all_keywords):
    feeds = [{"topic": t, "method": "keywordFilter"} for t in KEYWORD_TOPICS]
    for case in CASES:
        inp = case["input"]
        topic = inp.get("topic", "politics")
        got = topics_of(inp["headline"], inp.get("description"), feeds, all_keywords)
        assert (topic in got) is case["expected"]["match"], case["id"]


def test_topics_of_errors(all_keywords):
    feed = lambda **kw: [{"topic": "ai", "method": "keywordFilter", **kw}]
    with pytest.raises(ValueError):
        topics_of("x", None, [{"topic": "sport", "method": "feed"}], all_keywords)
    with pytest.raises(ValueError):
        topics_of("x", None, [{"topic": "ai", "method": "categoryFilter"}], all_keywords)
    with pytest.raises(ValueError):
        topics_of("x", None, [{"topic": "ai", "method": "magic"}], all_keywords)
    with pytest.raises(ValueError):
        topics_of("x", None, feed(), {})  # keywordFilter without a list
    with pytest.raises(ValueError):
        topics_of("x", None, [{"topic": "all-news", "method": "keywordFilter"}], all_keywords)
    assert topics_of("AI", None, [], all_keywords) == []
    assert topics_of("AI", None, feed() + feed(), all_keywords) == ["ai"]  # no duplicates


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
