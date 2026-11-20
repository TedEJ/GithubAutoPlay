"""Run the evaluation of the subagent-delegation skill as part of the checks.

The skill lives in .claude/skills/subagent-delegation/ and brings its own labelled
cases (tests/*.jsonl) and a scorer (tests/run_eval.py). This test fails when the
frontmatter is broken, when a case is under-powered, when any pick differs from its
label, or when a case file has lost cases.

The stress cases are scored with their flags, which were chosen knowing the labels:
that proves the flags are honoured, not that the keyword-only baseline is good.
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "subagent-delegation"
# Minimum number of labelled cases per file, so an emptied or truncated file cannot pass.
# Equal to the current counts: removing a case on purpose means lowering the number here.
CASE_FILES = {"cases.jsonl": 37, "holdout.jsonl": 12, "stress.jsonl": 14}


@pytest.fixture(autouse=True)
def clean_imports():
    """run_eval.py puts the skill's scripts folder on sys.path and imports
    pick_model; undo both after each test, and keep bytecode out of the skill."""
    saved_path, saved_modules = list(sys.path), set(sys.modules)
    saved_flag = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    yield
    sys.dont_write_bytecode = saved_flag
    sys.path[:] = saved_path
    for name in set(sys.modules) - saved_modules:
        del sys.modules[name]


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
    description = match.group(2)
    assert 0 < len(description) <= 1024
    # The regex is not a YAML parser: ": " or " #" would break real YAML parsing.
    assert ": " not in description and " #" not in description


def test_referenced_files_exist():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for ref in re.findall(r"`((?:references|scripts|tests)/[\w./-]+)`", text):
        assert (SKILL / ref).exists(), f"SKILL.md mentions {ref}, which is missing"


@pytest.mark.parametrize("name,minimum", CASE_FILES.items())
def test_cases_have_no_underpowered_or_wrong_answers(name, minimum, capsys):
    run_eval = load_eval()
    path = SKILL / "tests" / name
    cases = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(cases) >= minimum, f"{name} has {len(cases)} cases, expected at least {minimum}"
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


def test_eval_detects_an_overpowered_pick(tmp_path, capsys):
    """A pick that differs from its label without being weaker (an over-powered
    one) is no under-powering, but the case must still be reported as a MISS."""
    run_eval = load_eval()
    case = {"id": "too-much", "task": "Design the database schema", "model": "haiku", "effort": ["low"]}
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps(case) + "\n", encoding="utf-8")
    assert run_eval.run(path, use_flags=True) == 0
    assert "MISS" in capsys.readouterr().out


def test_announcement_goes_in_the_final_report():
    """Only a subagent's last message reaches the main agent, so the brief template and
    SKILL.md must put the announcement line in the final report, not in 'the reply'."""
    for name in ("SKILL.md", "references/brief-template.md"):
        text = (SKILL / name).read_text(encoding="utf-8")
        assert "final report" in text, f"{name} must say the line goes in the final report"
        assert "Start your reply" not in text, f"{name} still says 'Start your reply'"
