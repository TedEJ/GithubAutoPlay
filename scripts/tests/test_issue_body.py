import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import issue_body  # noqa: E402

TEMPLATES = SCRIPTS.parent / ".github" / "ISSUE_TEMPLATE"


def headings(text):
    return re.findall(r"^## .+$", text, flags=re.MULTILINE)


def make(gui=False, **kw):
    args = dict(goal="Do it.", depends_on="None", criteria=["It works"],
                tasks=["Step one"], notes=["A note"])
    if gui:
        args.update(gui=True, owner_checks=["Click the button"])
    args.update(kw)
    return issue_body.build_body(**args)


@pytest.mark.parametrize("gui,name", [(False, "task.md"), (True, "gui-task.md")])
def test_every_template_heading_in_order_and_no_front_matter(gui, name):
    template = (TEMPLATES / name).read_text(encoding="utf-8")
    body = make(gui)
    assert headings(body) == headings(template)
    assert "Depends on: None" in body
    assert not body.startswith("---")
    assert "<!--" not in body


def test_task_template_content():
    body = make()
    assert "## Goal\nDo it." in body
    assert "- [ ] Step one" in body
    assert "- A note" in body
    assert "## Acceptance criteria\n- It works" in body


def test_gui_template_keeps_fixed_lines_and_owner_checks():
    body = make(True)
    assert "- [ ] Update the README of the project" in body
    assert "- [ ] Run the tests of the project" in body
    assert "no-auto-merge" in body
    assert "Keep the GUI thin" in body
    assert "## Owner check\n- [ ] Click the button" in body


def test_depends_on_numbers():
    assert "Depends on: #12, #15\n" in make(depends_on="12, #15")


@pytest.mark.parametrize("bad", ["", "soon", "12;15", "#", "0", "-3"])
def test_bad_depends_on(bad):
    with pytest.raises(ValueError):
        make(depends_on=bad)


def test_missing_goal_criteria_and_owner_check():
    with pytest.raises(ValueError):
        make(goal=" ")
    with pytest.raises(ValueError):
        make(criteria=[])
    with pytest.raises(ValueError):
        make(True, owner_checks=[])
    with pytest.raises(ValueError):
        make(owner_checks=["x"])


def test_refuses_token_like_text():
    with pytest.raises(ValueError):
        make(goal="ghp_" + "a" * 20)


def test_cli_stdout_output_file_and_errors(tmp_path, capsys):
    assert issue_body.main(["--goal", "G", "--depends-on", "None",
                            "--criterion", "C"]) == 0
    assert "## Goal\nG" in capsys.readouterr().out
    out = tmp_path / "b.md"
    assert issue_body.main(["--goal", "G", "--depends-on", "3", "--criterion", "C",
                            "--output", str(out)]) == 0
    assert "Depends on: #3" in out.read_text(encoding="utf-8")
    assert issue_body.main(["--goal", "G", "--criterion", "C"]) == 2
    assert "issue_body.py:" in capsys.readouterr().err
