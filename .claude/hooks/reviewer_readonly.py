#!/usr/bin/env python3
"""PreToolUse hook for the Reviewer agent: allow read-only Bash commands only.

Claude Code passes the tool call as JSON on stdin. Exit code 0 allows the
command, exit code 2 blocks it and sends the message on stderr to the agent.

The hook is a strict allowlist. A command is allowed only when every part of
it (split on `&&`, `||`, `;` and `|`) is a known read or test command with
known-safe arguments. It refuses newlines, `$`, backticks, `~`, a lone `&`,
`<`, and `>` (except to /dev/null and `2>&1`), assignments before a command,
`{`, `}` and, outside grep patterns, wildcards, and any command word that contains a path (except the two scripts below).

Paths. The hook reads the working directory (`cwd`) from its JSON input and the
repository root from `CLAUDE_PROJECT_DIR` (default: two folders above this file).
`cd`, the path arguments of `python`, `node`, `bash`, `sh` and `scripts/check.sh`,
and the path after `git -C` are allowed when they resolve to a place inside the
repository, also when written as an absolute path (also a Windows path such as
`C:\\Users\\me\\repo` or `/c/Users/me/repo`). A path is refused when `..` takes it
out of the repository, when it is outside the root, when it holds a wildcard,
`~` or `$`, and when a symlink inside the repository points out of it. A `cd`
changes the folder that later relative paths in the same command are resolved from.
`python -W <value>` and `python -X <value>` are allowed for a short list of values
that only change how warnings or the interpreter report (error, ignore, default,
always, module, once; utf8, dev, faulthandler); `-W` can make a warning an error, which
only makes the run stricter, and neither option can load code or write files.

Known limits: this is a process guard, not a security boundary.
- `scripts/check.sh` and `scripts/check_reviewer.py` run code that is on the
  branch under review, and the tests run that branch's code as well.
- Files outside the repository can be read by the read commands (for example
  with `cat /etc/hosts`); only `cd`, git, the test runners and the two scripts are
  held to the repository.
- Symlinks inside the repository can point outside it. Git configuration (diff
  drivers, `--show-signature`) can run configured programs. The `/proc` block
  matches the literal text only. `tail -f` can hang.
- Running the tests can write caches such as `.pytest_cache`, and `git status`
  can refresh `.git/index`.
"""
import json
import ntpath
import os
import posixpath
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
WINDOWS_PATH = re.compile(r"^([A-Za-z]):[\\/]|^/([A-Za-z])/")

GLOB = re.compile(r"[*?\[]")
SAFE_WARNING = re.compile(r"^(error|ignore|default|always|module|once)(::[A-Za-z]+Warning)?$")
SAFE_XOPTION = {"utf8", "utf8=1", "dev", "faulthandler"}
PYTEST_FLAG = re.compile(r"^(-q|-qq|-v|-vv|-x|-s|--tb=\w+|-r\w+|--maxfail=\d+|--no-header|--co|--collect-only)$")
SAFE_STRIPPED = re.compile(r"(?<=\s)(2?>\s*/dev/null|2>&1)(?=\s|$|&&|\|\||[;|])")


class Context:
    """Where the repository is and which folder relative paths start from."""

    def __init__(self, root=None, cwd=None):
        self.root = root or os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.cwd = cwd or self.root


def _windows(path):
    """Return a normalised lower-case Windows path for `C:\\x`, `C:/x` and `/c/x`, else None."""
    m = WINDOWS_PATH.match(path)
    if not m:
        return None
    if m.group(2):
        path = m.group(2) + ":" + path[2:]
    return ntpath.normpath(path.replace("/", "\\")).lower()


def resolve(path, ctx):
    """Return the absolute, normalised location of `path` (and a flag for Windows style), or None."""
    path = path.split("::")[0]  # pytest node ids: file.py::test_name
    if not path or "\x00" in path:
        return None
    win = _windows(path)
    if win is not None:
        return win, True
    base_win = _windows(ctx.cwd)
    if base_win is not None and not path.startswith("/"):
        return ntpath.normpath(ntpath.join(base_win, path.replace("/", "\\"))).lower(), True
    full = posixpath.normpath(posixpath.join(ctx.cwd, path.replace("\\", "/")) if not path.startswith("/") else path)
    return full, False


def inside_repo(path, ctx):
    """True when `path` resolves to the repository root or a place under it."""
    if path.startswith("~") or "$" in path:
        return False
    found = resolve(path, ctx)
    if found is None:
        return False
    full, win = found
    root_win = _windows(ctx.root)
    if win:
        root = root_win if root_win is not None else None
        if root is None:
            return False
        return full == root or full.startswith(root.rstrip("\\") + "\\")
    if root_win is not None:
        return False
    root = posixpath.normpath(ctx.root)
    if not (full == root or full.startswith(root.rstrip("/") + "/")):
        return False
    real_root = os.path.realpath(root)
    real = os.path.realpath(full)  # follows symlinks that point out of the repository
    return real == real_root or real.startswith(real_root.rstrip("/") + "/")


def is_script(path, name, ctx):
    """True when `path` is the repository's own scripts/<name>."""
    found = resolve(path, ctx)
    target = resolve(os.path.join(ctx.root, "scripts", name) if _windows(ctx.root) is None else ctx.root + "/scripts/" + name, Context(ctx.root, ctx.root))
    return found is not None and target is not None and found[0] == target[0] and inside_repo(path, ctx)


def git_problem(args, ctx):
    if args[:1] == ["-C"]:
        if len(args) < 3 or not inside_repo(args[1], ctx):
            return "git -C is allowed only with a path inside the repository"
        args = args[2:]
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


def python_problem(args, ctx):
    while args and (args[0] in ("-W", "-X") or (args[0][:2] in ("-W", "-X") and len(args[0]) > 2)):
        flag = args[0][:2]
        value, args = (args[0][2:], args[1:]) if len(args[0]) > 2 else ((args[1] if len(args) > 1 else ""), args[2:])
        if flag == "-W" and not SAFE_WARNING.match(value):
            return f"python -W {value} is not on the list of safe values"
        if flag == "-X" and value not in SAFE_XOPTION:
            return f"python -X {value} is not on the list of safe values"
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
    if len(args) >= 1 and is_script(args[0], "check_reviewer.py", ctx):
        for a in args[1:]:
            if a.startswith("-") and a not in {"--body-file", "--changed-files"}:
                return f"check_reviewer option {a} is not allowed"
        return None
    return "python is allowed only as: python [-W value] -m pytest ... or scripts/check_reviewer.py"


def path_problem(cmd, args, ctx, local):
    if cmd == "cd":
        if len(args) != 1 or args[0].startswith("-"):
            return "cd takes exactly one path inside the repository"
        if GLOB.search(args[0]):
            return "wildcards in paths are not allowed"
        if not inside_repo(args[0], ctx):
            return "cd takes a path inside the repository only"
        return None
    for a in args:
        if GLOB.search(a) and not (cmd == "grep" and "/" not in a):
            return "wildcards in paths are not allowed"
        if "/proc" in a or a.startswith("/proc"):
            return "/proc paths are not allowed"
        if local:
            if a.startswith("@"):
                return f"{cmd} takes paths inside the repository only"
            if not a.startswith("-") and not inside_repo(a, ctx):
                return f"{cmd} takes paths inside the repository only"
    return None


def segment_problem(words, ctx):
    if not words:
        return "empty command part"
    cmd, args = words[0], words[1:]
    check_sh = is_script(cmd, "check.sh", ctx)
    local = cmd in LOCAL_ONLY or check_sh
    problem = path_problem(cmd, args, ctx, local)
    if problem:
        return problem
    if cmd == "git":
        return git_problem(args, ctx)
    if cmd in {"python", "python3"}:
        return python_problem(args, ctx)
    if cmd == "node":
        if args[:1] != ["--test"] or any(a.startswith("-") for a in args[1:]):
            return "node is allowed only as: node --test [paths]"
        return None
    if cmd in {"bash", "sh"} or check_sh:
        rest = args[1:] if cmd in {"bash", "sh"} else args
        if cmd in {"bash", "sh"} and not (args[:1] and is_script(args[0], "check.sh", ctx)):
            return "bash is allowed only for scripts/check.sh"
        return None if not any(a.startswith("-") for a in rest) else "scripts/check.sh takes no options"
    if cmd in READ_COMMANDS:
        return None
    return f"{cmd} is not on the Reviewer's read-only list"


def check(command, ctx=None):
    """Return None when the command is allowed, otherwise the reason."""
    ctx = ctx or Context()
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
        problem = segment_problem(words, ctx)
        if problem:
            return problem
        if words[0] == "cd":
            found = resolve(words[1], ctx)
            ctx.cwd = found[0]  # later relative paths start from the new folder
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
    cwd = data.get("cwd")
    problem = check(command, Context(cwd=cwd if isinstance(cwd, str) and cwd else None))
    if problem:
        print(f"Blocked: the Reviewer is read-only ({problem}).", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
