"""Run the evaluation of the subagent-delegation skill as part of the checks.

The skill lives in .claude/skills/subagent-delegation/ and brings its own labelled
cases (tests/*.jsonl) and a scorer (tests/run_eval.py). This test fails when the
frontmatter is broken, when a case is under-powered, or when any score drops.
"""
import importlib.util
import json
import re
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "subagent-delegation"
CASE_FILES = ["cases.jsonl", "holdout.jsonl", "stress.jsonl"]


def load_eval():
    spec = importlib.util.spec_from_file_location("skill_run_eval", SKILL / "tests" / "run_eval.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skill_frontmatter():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"---\nname: ([a-z0-9-]+)\ndescription: (.+)\n---\n", text)
    assert match, "SKILL.md must start with name and description frontmatter"
    assert match.group(1) == "subagent-delegation"
    assert 0 < len(match.group(2)) <= 1024


def test_referenced_files_exist():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for ref in re.findall(r"`((?:references|scripts|tests)/[\w./-]+)`", text):
        assert (SKILL / ref).exists(), f"SKILL.md mentions {ref}, which is missing"


@pytest.mark.parametrize("name", CASE_FILES)
def test_cases_have_no_underpowered_or_wrong_answers(name, capsys):
    run_eval = load_eval()
    path = SKILL / "tests" / name
    under = run_eval.run(path, use_flags=True)
    out = capsys.readouterr().out
    assert under == 0, f"under-powered cases in {name}:\n{out}"
    assert "MISS" not in out, f"cases missed in {name}:\n{out}"


def test_eval_detects_an_underpowered_pick(tmp_path, capsys):
    """The test above must be able to fail: a case labelled one tier above what
    the script picks has to be reported as under-powered."""
    run_eval = load_eval()
    case = {"id": "too-hard", "task": "Grep app.log for ERROR lines", "model": "opus", "effort": ["high"]}
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps(case) + "\n", encoding="utf-8")
    assert run_eval.run(path, use_flags=True) == 1
    assert "MISS" in capsys.readouterr().out
