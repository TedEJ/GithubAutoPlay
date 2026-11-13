"""Headline cleaning (R1.3) against the shared cases."""
import json
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


def test_shared_file_has_the_three_sections():
    assert set(SHARED) == {"cleaning", "time", "keywords"}
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
