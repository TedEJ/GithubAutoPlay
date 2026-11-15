"""Headline cleaning (R1.3) against the shared cases."""
import json
import time
from pathlib import Path

import pytest

from newsreader.select import clean_headline

CASES_FILE = Path(__file__).resolve().parent / "shared-cases.json"
SHARED = json.loads(CASES_FILE.read_text(encoding="utf-8"))
CLEANING = SHARED.get("cleaning", [])

REQUIRED_KINDS = [
    "tags", "named-entities", "numeric-entities", "double-encoded", "whitespace",
    "unicode", "empty", "whitespace-only", "very-long",
]


def test_shared_file_has_its_sections():
    assert set(SHARED) == {"cleaning", "time", "keywords", "topics"}
    for section in SHARED.values():
        assert isinstance(section, list)


def test_cleaning_cases_have_id_input_expected():
    ids = [c["id"] for c in CLEANING]
    assert len(ids) == len(set(ids))
    for case in CLEANING:
        assert set(case) == {"id", "input", "expected"}
        assert isinstance(case["input"], str) and isinstance(case["expected"], str)


def test_cleaning_cases_cover_the_required_kinds():
    ids = " ".join(c["id"] for c in CLEANING)
    for kind in REQUIRED_KINDS:
        assert kind in ids, kind
    assert any(len(c["input"]) > 300 for c in CLEANING)


@pytest.mark.parametrize("case", CLEANING, ids=[c["id"] for c in CLEANING])
def test_shared_cleaning_case(case):
    assert clean_headline(case["input"]) == case["expected"]


def test_cleaning_is_not_cut_or_changed_beyond_r1_3():
    text = "x" * 5000
    assert clean_headline(text) == text


def test_very_long_numeric_entities_are_left_unchanged():
    for text in ("&#" + "9" * 5000 + ";", "&#x" + "F" * 5000 + ";"):
        assert clean_headline(text) == text


def test_numeric_entities_with_leading_zeros_still_decode():
    assert clean_headline("&#0000065;") == "A"
    assert clean_headline("&#x0000041;") == "A"
    assert clean_headline("&#" + "0" * 5000 + "65;") == "A"
    assert clean_headline("&#x" + "0" * 5000 + "41;") == "A"


def test_invalid_numeric_entities_stay_literal():
    for text in ("&#0;", "&#" + "0" * 5000 + ";", "&#xD800;", "&#55296;",
                 "&#1114112;", "&#x110000;"):
        assert clean_headline(text) == text
    assert clean_headline("&#1114111;") == "\U0010FFFF"
    assert clean_headline("&#x10FFFF;") == "\U0010FFFF"


def _timed(text):
    start = time.perf_counter()
    result = clean_headline(text)
    return result, time.perf_counter() - start


def test_many_unterminated_comment_starts_are_cleaned_in_linear_time():
    text = "<!--" * 20000
    result, seconds = _timed(text)
    assert result == text
    assert seconds < 1.0


def test_unterminated_comment_starts_do_not_hide_later_tags_or_a_late_end():
    text = "<!--" * 20000
    result, seconds = _timed(text + "<b>x</b>")
    assert result == text + "x"
    assert seconds < 1.0
    result, seconds = _timed(text + " a --> b")
    assert result == "b"
    assert seconds < 1.0


def test_comment_starts_after_the_last_comment_end_are_kept_in_linear_time():
    text = "a<!-- c -->" + "<!--" * 20000 + "z"
    result, seconds = _timed(text)
    assert result == "a" + "<!--" * 20000 + "z"
    assert seconds < 1.0


def test_other_unterminated_markup_is_cleaned_in_linear_time():
    for text in ("<a" * 50000, "</" + "a" * 100000, "<a " * 50000 + "b", "<!" * 50000):
        result, seconds = _timed(text)
        assert result == text
        assert seconds < 1.0
