#!/usr/bin/env python3
"""Write a pull request description in the format of
.github/pull_request_template.md and print it to standard output.

Example:
    python3 scripts/pr_body.py --issue 42 --summary "Adds a start screen." \\
        --gates-passed --workload right --no-auto-merge \\
        --reviewer-verdict ok --reviewer-summary "No must-fix findings." \\
        --owner-check "The start screen shows three buttons"

Nothing is written to disk and nothing is sent anywhere. The script refuses
text that looks like a GitHub token. Use --footer for lines that must end the
description (for example a link added by the person or tool that opens the
pull request); the script never adds a link of its own.
"""

import argparse
import re
import sys

GATES = [
    "Scope: the diff contains only what the issue asks for",
    "Acceptance criteria: every criterion in the issue is met",
    "Documentation: README and WORKFLOW.md are updated if behaviour or process changed",
    "Tests: the required check `checks` is green (and new tests were added for new code)",
]
WORKLOAD = {
    "right": "Right level",
    "low": "Too low (should have been higher)",
    "high": "Too high (should have been lower)",
}
VERDICTS = {"ok": "OK", "must-fix": "Must fix"}
DOCS_ONLY_VERDICT = "Not needed (documentation only)"
TOKEN_PATTERN = re.compile(r"(github_pat_|gh[pousr]_)[A-Za-z0-9_]{10,}")


def box(checked, text):
    return f"- [{'x' if checked else ' '}] {text}"


def build_body(issue, summary, closes=False, gates_passed=False,
               workload=None, no_auto_merge=False, owner_checks=(), footer="",
               reviewer_verdict=None, reviewer_summary="", docs_only=False):
    """Return the pull request description as a string."""
    if issue < 1:
        raise ValueError("issue must be a positive number")
    if workload is not None and workload not in WORKLOAD:
        raise ValueError(f"workload must be one of {sorted(WORKLOAD)}")
    if reviewer_verdict is not None and reviewer_verdict not in VERDICTS:
        raise ValueError(f"reviewer verdict must be one of {sorted(VERDICTS)}")
    for text in [summary, footer, reviewer_summary, *owner_checks]:
        if TOKEN_PATTERN.search(text):
            raise ValueError("the text looks like it contains a GitHub token")

    if reviewer_verdict is not None:
        verdict = VERDICTS[reviewer_verdict]
    elif docs_only:
        verdict = DOCS_ONLY_VERDICT
    else:
        verdict = "pending"
    reviewer = ["## Reviewer", f"Verdict: {verdict}"]
    if reviewer_summary.strip():
        reviewer += ["", reviewer_summary.strip()]
    reviewer.append("")

    word = "Closes" if closes else "Refs"
    parts = [
        "## Summary",
        summary.strip(),
        "",
        "## Issue",
        f"{word} #{issue}",
        "",
        "The owner closes the issue after the merge.",
        "",
    ]
    if no_auto_merge:
        parts += [
            "## Owner check before merging",
            "This pull request has the label `no-auto-merge`. Please test it locally and confirm:",
            *[box(False, item) for item in owner_checks],
            "",
        ]
    parts += [
        "## Verification gates",
        *[box(gates_passed, gate) for gate in GATES],
        "",
        *reviewer,
        "## Workload level",
        "Was the workload label on the issue right?",
        "",
        *[box(workload == key, text) for key, text in WORKLOAD.items()],
        "",
        "<!-- This feedback is used to make the next workload estimates better. -->",
    ]
    body = "\n".join(parts) + "\n"
    if footer.strip():
        body += "\n" + footer.strip() + "\n"
    return body


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--issue", type=int, required=True, help="issue number")
    parser.add_argument("--summary", required=True, help="what changed and why")
    parser.add_argument("--closes", action="store_true",
                        help="write 'Closes #N' instead of 'Refs #N'")
    parser.add_argument("--gates-passed", action="store_true",
                        help="tick the four verification gates")
    parser.add_argument("--workload", choices=sorted(WORKLOAD),
                        help="tick the workload feedback: right, low or high")
    parser.add_argument("--no-auto-merge", action="store_true",
                        help="add the owner check section")
    parser.add_argument("--owner-check", action="append", default=[],
                        help="one owner check item (repeat for more)")
    parser.add_argument("--reviewer-verdict", choices=sorted(VERDICTS),
                        help="the Reviewer's verdict: ok or must-fix")
    parser.add_argument("--reviewer-summary", default="",
                        help="short summary of the Reviewer's findings")
    parser.add_argument("--docs-only", action="store_true",
                        help="documentation-only change: no Reviewer verdict needed")
    parser.add_argument("--footer", default="", help="text added at the very end")
    args = parser.parse_args(argv)
    if args.reviewer_verdict is None and not args.docs_only:
        print("pr_body.py: give --reviewer-verdict (ok or must-fix), or "
              "--docs-only for a documentation-only change", file=sys.stderr)
        return 2
    try:
        body = build_body(
            args.issue, args.summary, closes=args.closes,
            gates_passed=args.gates_passed, workload=args.workload,
            no_auto_merge=args.no_auto_merge, owner_checks=args.owner_check,
            footer=args.footer, reviewer_verdict=args.reviewer_verdict,
            reviewer_summary=args.reviewer_summary, docs_only=args.docs_only,
        )
    except ValueError as error:
        print(f"pr_body.py: {error}", file=sys.stderr)
        return 2
    sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
