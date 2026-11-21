#!/usr/bin/env python3
"""Write an issue description in the format of the issue templates in
.github/ISSUE_TEMPLATE/ and print it to standard output.

`gh issue create` does not apply the templates, so the manager writes the body
with this script and passes it with --body-file. Example:

    python3 scripts/issue_body.py --goal "Add a start screen." \\
        --task "Write the screen" --depends-on None \\
        --criterion "The screen shows three buttons" --output body.md
    gh issue create --title "..." --body-file body.md --label Medium

Use --gui for the GUI template (it also needs at least one --owner-check).
The script reads the template file itself, so the sections stay in sync with
it: the front matter is dropped, headings keep the template order, comment
placeholders are replaced by the given text and fixed lines are kept. It does
not call gh or the network, does not set labels (give --label Low, Medium or
High to gh) and refuses text that looks like a GitHub token.
"""

import argparse
import re
import sys
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / ".github" / "ISSUE_TEMPLATE"
TEMPLATES = {False: "task.md", True: "gui-task.md"}
TOKEN_PATTERN = re.compile(r"(github_pat_|gh[pousr]_)[A-Za-z0-9_]{10,}")
PLACEHOLDERS = {"-", "- [ ]"}


def normalize_depends(value):
    """Return the text after 'Depends on: ' or raise ValueError."""
    value = (value or "").strip()
    if not value:
        raise ValueError("--depends-on is required: None or issue numbers such as 12,15")
    if value.lower() == "none":
        return "None"
    numbers = [part.strip().lstrip("#") for part in value.split(",")]
    if not all(re.fullmatch(r"[1-9][0-9]*", n) for n in numbers):
        raise ValueError(f"bad --depends-on value {value!r}: use None or issue "
                         "numbers such as 12,15")
    return ", ".join(f"#{n}" for n in numbers)


def read_template(gui=False):
    """Return the template as a list of (heading line, content lines)."""
    text = (TEMPLATE_DIR / TEMPLATES[gui]).read_text(encoding="utf-8")
    text = text.replace("\r\n", "\n")
    if text.startswith("---\n"):
        if "\n---\n" not in text:
            raise ValueError(f"template {TEMPLATES[gui]} has an opening --- "
                             "but no closing --- in its front matter")
        text = text.split("\n---\n", 1)[1]
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    sections = []
    for line in text.split("\n"):
        line = line.rstrip()
        if line.startswith("## "):
            sections.append((line, []))
        elif sections and line:
            sections[-1][1].append(line)
    return sections


def build_body(goal, depends_on, criteria, tasks=(), notes=(), owner_checks=(),
               gui=False):
    """Return the issue description as a string."""
    goal = (goal or "").strip()
    if not goal:
        raise ValueError("--goal is required")
    depends = normalize_depends(depends_on)
    criteria = [c.strip() for c in criteria if c.strip()]
    if not criteria:
        raise ValueError("at least one --criterion is required")
    tasks = [t.strip() for t in tasks if t.strip()]
    if not gui and not tasks:
        raise ValueError("at least one --task is required for the task template")
    notes = [n.strip() for n in notes if n.strip()]
    owner_checks = [o.strip() for o in owner_checks if o.strip()]
    if gui and not owner_checks:
        raise ValueError("the GUI template needs at least one --owner-check")
    if owner_checks and not gui:
        raise ValueError("--owner-check is only used with --gui")
    for text in [goal, *tasks, *notes, *criteria, *owner_checks]:
        if TOKEN_PATTERN.search(text):
            raise ValueError("the text looks like it contains a GitHub token")

    parts = []
    for heading, lines in read_template(gui):
        name = heading[3:].strip()
        fixed = [ln for ln in lines if ln.strip() not in PLACEHOLDERS
                 and not ln.startswith("Depends on:")]
        out = [heading]
        if name == "Goal":
            out.append(goal)
        elif name == "Tasks":
            out += [f"- [ ] {t}" for t in tasks] + fixed
        elif name == "Notes":
            out += [f"Depends on: {depends}"] + fixed + [f"- {n}" for n in notes]
        elif name == "Owner check":
            out += [f"- [ ] {o}" for o in owner_checks] + fixed
        elif name == "Acceptance criteria":
            out += [f"- {c}" for c in criteria]
        else:
            out += fixed
        parts.append("\n".join(out))
    return "\n\n".join(parts) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--gui", action="store_true",
                        help="use .github/ISSUE_TEMPLATE/gui-task.md")
    parser.add_argument("--goal", default="", help="one or two sentences")
    parser.add_argument("--task", action="append", default=[],
                        help="one task (repeat; at least one unless --gui)")
    parser.add_argument("--note", action="append", default=[],
                        help="one note (repeat for more)")
    parser.add_argument("--depends-on", default="",
                        help="None, or issue numbers such as 12,15 (required)")
    parser.add_argument("--criterion", action="append", default=[],
                        help="one acceptance criterion (repeat; at least one)")
    parser.add_argument("--owner-check", action="append", default=[],
                        help="one owner check (GUI template; repeat for more)")
    parser.add_argument("--output", help="write to this file instead of stdout")
    args = parser.parse_args(argv)
    try:
        body = build_body(args.goal, args.depends_on, args.criterion,
                          tasks=args.task, notes=args.note,
                          owner_checks=args.owner_check, gui=args.gui)
    except ValueError as error:
        print(f"issue_body.py: {error}", file=sys.stderr)
        return 2
    if args.output:
        Path(args.output).write_text(body, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
