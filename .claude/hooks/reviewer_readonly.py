#!/usr/bin/env python3
"""PreToolUse hook for the Reviewer agent: allow read-only Bash commands only.

Claude Code passes the tool call as JSON on stdin. Exit code 0 allows the
command, exit code 2 blocks it and sends the message on stderr to the agent.

The hook is a strict allowlist. A command is allowed only when every part of
it (split on `&&`, `||`, `;` and `|`) is a known read or test command with
known-safe arguments. It refuses newlines, `$`, backticks, `~`, a lone `&`,
`<`, and `>` (except to /dev/null and `2>&1`), assignments before a command,
`{`, `}` and, outside grep patterns, wildcards, and any command word that contains a path (except the two scripts below).

Known limits: this is a process guard, not a security boundary.
- `scripts/check.sh` and `scripts/check_reviewer.py` run code that is on the
  branch under review, and the tests run that branch's code as well.
- Files outside the repository can be read (for example with `cat /etc/hosts`).
- Symlinks inside the repository can point outside it. Git configuration (diff
  drivers, `--show-signature`) can run configured programs. The `/proc` block
  matches the literal text only. `tail -f` can hang.
- Running the tests can write caches such as `.pytest_cache`, and `git status`
  can refresh `.git/index`.
"""
import json
import re
import shlex
import sys

OPERATORS = {"&&", "||", ";", "|"}
READ_COMMANDS = {
    "cat", "head", "tail", "ls", "grep", "wc", "cut", "diff", "stat", "echo",
    "pwd", "cd", "basename", "dirname",
}
GIT_READ = {
    "diff", "log", "show", "status", "rev-parse", "ls-files", "blame",
    "rev-list", "merge-base", "ls-tree", "shortlog", "diff-tree", "branch",
}
GIT_FORBIDDEN_OPTIONS = (
    "--output", "--ext-diff", "--textconv", "--no-index", "--open-files-in-pager",
    "-O", "--exec-path", "--git-dir", "--work-tree", "--paginate", "-c", "-C",
    "--help", "-h", "--out", "--ext", "--tex",
)
GIT_BRANCH_OPTIONS = {"--list", "-l", "-a", "-r", "--show-current", "-v", "-vv", "--all", "--remotes"}
LOCAL_ONLY = {"cd", "python", "python3", "node", "bash", "sh", "scripts/check.sh"}
GLOB = re.compile(r"[*?\[]")
PYTEST_FLAG = re.compile(r"^(-q|-qq|-v|-vv|-x|-s|--tb=\w+|-r\w+|--maxfail=\d+|--no-header|--co|--collect-only)$")
SAFE_STRIPPED = re.compile(r"(?<=\s)(2?>\s*/dev/null|2>&1)(?=\s|$|&&|\|\||[;|])")


def git_problem(args):
    if not args or args[0].startswith("-"):
        return "git options before the subcommand are not allowed"
    sub, rest = args[0], args[1:]
    if sub not in GIT_READ:
        return f"git {sub} is not read-only"
    for a in rest:
        if a == "--":
            break
        for bad in GIT_FORBIDDEN_OPTIONS:
            if a == bad or (a.startswith(bad) and (bad.startswith("--") or len(a) > len(bad))):
                return f"git option {a} is not allowed"
    if sub == "branch":
        if any(a.startswith("-") and a not in GIT_BRANCH_OPTIONS for a in rest):
            return "git branch is allowed only for listing"
        if any(not a.startswith("-") for a in rest) and "--list" not in rest and "-l" not in rest:
            return "git branch with a name would create a branch"
    return None


def python_problem(args):
    if args[:2] == ["-m", "pytest"]:
        rest, i = args[2:], 0
        while i < len(rest):
            a = rest[i]
            if a == "-k":
                i += 2
                continue
            if a.startswith("-") and not PYTEST_FLAG.match(a):
                return f"pytest option {a} is not allowed"
            i += 1
        return None
    if args[:1] == ["scripts/check_reviewer.py"]:
        rest = args[1:]
        for i, a in enumerate(rest):
            if a.startswith("-") and a not in {"--body-file", "--changed-files"}:
                return f"check_reviewer option {a} is not allowed"
        return None
    return "python is allowed only as: python -m pytest ..."


def path_problem(cmd, args):
    if cmd == "cd" and (len(args) != 1 or args[0].startswith("-")):
        return "cd takes exactly one path inside the repository"
    for a in args:
        if GLOB.search(a) and not (cmd == "grep" and "/" not in a):
            return "wildcards in paths are not allowed"
        if "/proc" in a or a.startswith("/proc"):
            return "/proc paths are not allowed"
        if cmd in LOCAL_ONLY and (a.startswith("/") or a.startswith("@") or ".." in a.split("/")):
            return f"{cmd} takes paths inside the repository only"
    return None


def segment_problem(words):
    if not words:
        return "empty command part"
    cmd, args = words[0], words[1:]
    problem = path_problem(cmd, args)
    if problem:
        return problem
    if cmd == "git":
        return git_problem(args)
    if cmd in {"python", "python3"}:
        return python_problem(args)
    if cmd == "node":
        if args[:1] != ["--test"] or any(a.startswith("-") for a in args[1:]):
            return "node is allowed only as: node --test [paths]"
        return None
    if cmd in {"bash", "sh"} or cmd == "scripts/check.sh":
        rest = args[1:] if cmd in {"bash", "sh"} else args
        if cmd in {"bash", "sh"} and args[:1] != ["scripts/check.sh"]:
            return "bash is allowed only for scripts/check.sh"
        return None if not any(a.startswith("-") for a in rest) else "scripts/check.sh takes no options"
    if cmd in READ_COMMANDS:
        return None
    return f"{cmd} is not on the Reviewer's read-only list"


def check(command):
    """Return None when the command is allowed, otherwise the reason."""
    if not command.strip():
        return None
    if "\n" in command or "\r" in command:
        return "newlines are not allowed"
    for ch, name in (("$", "variables and substitution"), ("`", "backticks"), ("~", "~ paths"), ("{", "brace expansion"), ("}", "brace expansion")):
        if ch in command:
            return f"{name} are not allowed"
    stripped = SAFE_STRIPPED.sub("", " " + command + " ")
    lexer = shlex.shlex(stripped, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""  # bash starts a comment only at the start of a word
    try:
        tokens = list(lexer)
    except ValueError:
        return "cannot parse the command"
    parts, current = [], []
    for t in tokens:
        if t in OPERATORS:
            parts.append(current)
            current = []
        elif re.fullmatch(r"[();&|<>]+", t):
            return f"the operator {t} is not allowed"
        else:
            current.append(t)
    parts.append(current)
    for words in parts:
        problem = segment_problem(words)
        if problem:
            return problem
    return None


def main():
    try:
        data = json.load(sys.stdin)
        tool_input = data.get("tool_input") or {}
        command = tool_input.get("command", "")
        if not isinstance(command, str):
            raise ValueError
    except (ValueError, AttributeError):
        print("Reviewer hook: could not read the tool call.", file=sys.stderr)
        return 2
    if data.get("tool_name", "Bash") != "Bash":
        return 0
    problem = check(command)
    if problem:
        print(f"Blocked: the Reviewer is read-only ({problem}).", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
