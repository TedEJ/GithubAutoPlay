import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import check_reviewer  # noqa: E402
import pr_body  # noqa: E402


def body(**kwargs):
    return pr_body.build_body(1, "x", **kwargs)


def test_ok_passes():
    assert check_reviewer.check(body(reviewer_verdict="ok"), ["a.py"]) == []


def test_missing_section_fails():
    assert check_reviewer.check("## Summary\nx\n", ["a.py"])


def test_pending_and_must_fix_fail():
    assert check_reviewer.check(body(), ["a.py"])
    assert check_reviewer.check(body(reviewer_verdict="must-fix"), ["a.py"])


def test_docs_only_needs_only_markdown_files():
    docs = body(docs_only=True)
    assert check_reviewer.check(docs, ["README.md", "x/design.md"]) == []
    assert check_reviewer.check(docs, ["README.md", "a.py"])
    assert check_reviewer.check(docs, [])


def test_verdict_is_read_only_inside_the_reviewer_section():
    text = "## Summary\nVerdict: OK\n\n## Reviewer\nVerdict: pending\n"
    assert check_reviewer.check(text, ["a.py"])


def test_main_reads_files_and_sets_exit_code(tmp_path):
    (tmp_path / "b.txt").write_text(body(reviewer_verdict="ok"), encoding="utf-8")
    (tmp_path / "f.txt").write_text("a.py\n", encoding="utf-8")
    args = ["--body-file", str(tmp_path / "b.txt"), "--changed-files", str(tmp_path / "f.txt")]
    assert check_reviewer.main(args) == 0
    (tmp_path / "b.txt").write_text(body(), encoding="utf-8")
    assert check_reviewer.main(args) == 1
