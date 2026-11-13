#!/usr/bin/env python3
"""Fail unless a pull request description carries an OK from the Reviewer.

Used by the CI job `checks`. Usage:

    python3 scripts/check_reviewer.py --body-file body.txt --changed-files files.txt

The body file holds the pull request description; the changed-files file holds
one path per line. The description needs a section `## Reviewer` with a line
`Verdict: OK`. A pull request that changes only Markdown files may use
`Verdict: Not needed (documentation only)`, and that is accepted only when
every changed file really is a Markdown file. This is a process rule: it checks
what the description says, not who wrote it.
"""

import argparse
import re
import sys

OK = "ok"
DOCS_ONLY = "not needed (documentation only)"


def find_verdict(body):
    """Return the lower-case verdict in the Reviewer section, or None."""
    match = re.search(r"^## Reviewer[ \t]*$(.*?)(?=^## |\Z)", body,
                      flags=re.MULTILINE | re.DOTALL)
    if not match:
        return None
    line = re.search(r"^Verdict:[ \t]*(.+?)[ \t]*$", match.group(1), flags=re.MULTILINE)
    return line.group(1).lower() if line else None


def only_markdown(changed_files):
    files = [f for f in changed_files if f.strip()]
    return bool(files) and all(f.strip().lower().endswith(".md") for f in files)


def check(body, changed_files):
    """Return a list of problems; an empty list means the check passes."""
    verdict = find_verdict(body)
    if verdict is None:
        return ["The pull request description has no 'Verdict:' line in a '## Reviewer' section."]
    if verdict == OK:
        return []
    if verdict == DOCS_ONLY:
        if only_markdown(changed_files):
            return []
        return ["'Not needed (documentation only)' is only allowed when every changed file is a Markdown file."]
    if verdict == "must fix":
        return ["The Reviewer's verdict is 'Must fix'. Fix the findings and ask the Reviewer again."]
    return [f"The Reviewer's verdict is '{verdict}', not 'OK'."]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--body-file", required=True)
    parser.add_argument("--changed-files", required=True)
    args = parser.parse_args(argv)
    with open(args.body_file, encoding="utf-8") as handle:
        body = handle.read()
    with open(args.changed_files, encoding="utf-8") as handle:
        changed = handle.read().splitlines()
    problems = check(body, changed)
    for problem in problems:
        print(f"::error::{problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
