#!/usr/bin/env python3
"""PreToolUse hook for the Designer/Developer agent: block push, GitHub and network commands.

Claude Code passes the tool call as JSON on stdin. Exit code 0 allows the call,
exit code 2 blocks it and sends the message on stderr to the agent.

This is a denylist, because the agent needs normal git, tests and file editing.
It blocks:
- `git push` in all common forms (also with global options such as `-C` or `--git-dir`
  before it), `git send-pack`, `git http-push`, `git credential*`, every `git -c`
  and `git --config-env`, `git remote` other than listing, and `git config` other
  than reading;
- `gh`, `curl`, `wget`, `Invoke-WebRequest` and `Invoke-RestMethod` (and their
  aliases), `ssh`, `scp`, `sftp`, `ftp`, `rsync`, `nc`, `ncat`, `telnet`,
  `certutil`, `bitsadmin`, and shells that cannot be checked here (`powershell`,
  `pwsh`, `cmd`);
- text that names a credential file or secret (`.git-credentials`, `.netrc`,
  `.ssh`, `.env`, `.config/gh`, `.aws`, ...), token variables and token prefixes,
  and `printenv`/`env` dumps. The same names are refused in the paths of `Read`,
  `Grep` and `Glob`, and `Write` and `Edit` may not write inside `.git`.

`git fetch`, `git pull` and package installs (`pip install`, `npm install`) are
allowed on purpose: they read, and the agent may need them. `git config` is
allowed only for reading one name (`git config user.name`) or with `--get` or
`--list`, and never for names that contain `credential`; `git remote` only bare,
with `-v` or `get-url`.

The command is split on `&&`, `||`, `;`, `|`, `&`, newlines, parentheses,
braces, backticks and `$(`, so a blocked command inside a chain or a command
substitution is found. Wrappers (`env`, `sudo`, `time`, `nohup`, `timeout`,
`xargs`, `find -exec`, `bash -c`, `eval`, ...) are looked through. Words inside
quotes that are only arguments (a commit message that says "git push") are not
blocked.

Known limits: this is a process guard, not a security boundary. A denylist
cannot stop every way to reach the network or GitHub.
- A Python or Node script (or the project's tests) can open a connection, and
  the tests run code from the branch. So can a shell script that the agent
  writes and then runs; `bash` or `sh` without a script or `-c` text is blocked,
  but the content of a script file is not read.
- A git alias set outside the repository (in the user's own configuration) can
  hide `push`; `git config` writes and `git -c` are blocked, but not an alias
  that already exists.
- Obfuscation that builds a command word at run time (variables, `base64`) is
  refused only where `$` shows up in a command word or before a git subcommand.
- Network tools that are not on the list (for example a program the agent
  builds or installs) are not blocked.
- Text that is stripped before checking, such as the body of a quoted heredoc,
  is never read; the rest of its first line (for example `| sh`) is.
- Credentials that are saved in the operating system are used by git without
  the agent reading them, so `git push` must stay blocked.
"""
import json
import os
import re
import shlex
import sys

NETWORK_COMMANDS = {
    "gh", "curl", "wget", "invoke-webrequest", "iwr", "invoke-restmethod", "irm",
    "ssh", "scp", "sftp", "ftp", "rsync", "nc", "ncat", "netcat", "telnet",
    "certutil", "bitsadmin", "start-bitstransfer", "busybox", "socat", "openssl",
    "nslookup", "dig", "ping", "lynx", "aria2c", "tftp", "xdg-open",
}
UNCHECKABLE_SHELLS = {"powershell", "pwsh", "cmd"}
POSIX_SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
WRAPPERS = {
    "env", "sudo", "doas", "command", "builtin", "exec", "time", "nohup", "nice",
    "ionice", "stdbuf", "setsid", "xargs", "watch", "timeout", "then", "do",
    "else", "elif", "if", "while", "until", "!", "parallel", "script", "su",
    "runuser", "flock", "strace", "ltrace", "chroot", "unshare", "taskset", "chrt",
}
REDIRECT = re.compile(r"^\d*(>>?|<)")
WRAPPER_VALUE_OPTIONS = {"-u", "-n", "-s", "-t", "-d", "-i", "-e", "-I", "-P", "-a", "-o", "-E"}
GIT_ALWAYS_BLOCKED = {"push", "send-pack", "http-push", "remote-http", "remote-https"}
GIT_GLOBAL_WITH_VALUE = {"-C", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--attr-source"}
GIT_CONFIG_WRITE_OPTIONS = {"--add", "--replace-all", "--unset", "--unset-all", "--edit", "-e", "--rename-section", "--remove-section"}
GIT_CONFIG_READ = {"--get", "--get-all", "--get-regexp", "--list", "-l", "--show-origin", "--show-scope", "--name-only", "-z", "--null", "--local", "--global", "--system", "--worktree"}
GIT_RUNS_COMMANDS = {("submodule", "foreach"), ("bisect", "run")}
SECRET_PATTERN = re.compile(
    r"(\.git-credentials|(^|[\\/\s=:'\"])_?\.?netrc\b|\.ssh\b|\bid_(rsa|dsa|ecdsa|ed25519)\b|"
    r"(^|[\\/\s=:'\"])\.env(?!\.(example|sample|template)\b)(\.\w+)?(\s|$|['\"/\\])|\.config[\\/]gh\b|[\\/]gh[\\/]hosts\.yml|/dev/(tcp|udp)/|"
    r"\.aws\b|\.npmrc\b|\.pypirc\b|\.docker[\\/]config|credentials\.json|\.gnupg\b|\.kube\b|"
    r"\.claude[\\/]projects|\.claude\.json|\bGIT_(CONFIG\w*|ASKPASS|SSH\w*|EXEC_PATH)\b|"
    r"\b(github_pat_|ghp_|gho_|ghu_|ghs_|ghr_)|"
    r"\b(GITHUB_TOKEN|GH_TOKEN|GH_ENTERPRISE_TOKEN|GITHUB_ENTERPRISE_TOKEN|ANTHROPIC_API_KEY)\b|"
    r"\bgit[ -]credential\b)",
    re.IGNORECASE,
)
OPERATOR_CHARS = set(";|&\n\r(){}`")
HEREDOC = re.compile(r"<<-?\s*(['\"])(\w+)\1([^\n]*)\n.*?\n[ \t]*\2[ \t]*(?=\n|$)", re.DOTALL)
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
MAX_DEPTH = 6


def command_name(word):
    name = re.split(r"[\\/]", word)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def git_problem(args, i=0):
    """Check git's arguments. An option such as `--namespace` may or may not take the
    next word as its value, so both readings are checked."""
    while i < len(args) and args[i].startswith("-") and args[i] != "--":
        a = args[i]
        if "$" in a or "`" in a:
            return "a variable in git's options cannot be checked"
        if a == "-c" or a.startswith("-c") and len(a) > 2 and a[2] != "-" and not a.startswith("-C"):
            return "git -c can set aliases and credentials"
        if a.startswith("--config-env"):
            return "git --config-env can set aliases and credentials"
        if a in GIT_GLOBAL_WITH_VALUE:
            return git_problem(args, i + 1) or git_problem(args, i + 2)
        i += 1
    if i >= len(args):
        return None
    sub, rest = re.split(r"[<>]", args[i])[0].lower(), args[i + 1:]
    if "$" in sub or "`" in sub:
        return "a variable in place of the git subcommand cannot be checked"
    if sub in GIT_ALWAYS_BLOCKED:
        return f"git {sub} is not allowed"
    if sub.startswith("credential"):
        return "git credential commands are not allowed"
    for key, word in GIT_RUNS_COMMANDS:
        if sub == key and word in rest:
            inner = " ".join(rest[rest.index(word) + 1:])
            return text_problem(inner, 1) or f"git {key} {word} runs other commands and is not allowed"
    if sub == "rebase":
        for idx, a in enumerate(rest):
            value = rest[idx + 1] if a in ("-x", "--exec") and idx + 1 < len(rest) else a.partition("=")[2] if a.startswith("--exec=") else None
            if value is not None:
                return text_problem(value, 1) or "git rebase --exec runs other commands and is not allowed"
    if sub == "remote":
        if any(a not in ("-v", "--verbose", "get-url") and not (rest[:1] == ["get-url"]) for a in rest):
            return "git remote may only list remotes or show get-url"
    if sub == "config":
        options = [a for a in rest if a.startswith("-")]
        names = [a for a in rest if not a.startswith("-")]
        if any(re.search(r"credential", n, re.I) for n in names):
            return "git config on credentials is not allowed"
        if any(o in GIT_CONFIG_WRITE_OPTIONS or o not in GIT_CONFIG_READ for o in options):
            return "git config may only read (one name, --get or --list)"
        if not any(o in GIT_CONFIG_READ and o not in ("--local", "--global", "--system", "--worktree") for o in options) and len(names) > 1:
            return "git config may only read (one name, --get or --list)"
    return None


def words_problem(words, depth, strict=True):
    """`strict` is False when the first word is only a guess at where a command starts."""
    if depth > MAX_DEPTH:
        return "the command is nested too deeply to check"
    words = list(words)
    had_assignment = False
    while words and (ASSIGNMENT.match(words[0]) or REDIRECT.match(words[0])):
        w = words.pop(0)
        if ASSIGNMENT.match(w):
            had_assignment = True
        elif re.fullmatch(r"\d*(>>?|<)&?", w) and words:
            words.pop(0)  # the target of a redirection written as `> file`
    if words and words[0] == "$SUBST" and had_assignment:
        return None  # `x=$(...)` only assigns
    if words and command_name(words[0]) in WRAPPERS:
        wrapper = command_name(words[0])
        rest = words[1:]
        if wrapper == "env" and all(w.startswith("-") or ASSIGNMENT.match(w) for w in rest):
            return "printing the environment can show tokens"
        # Wrapper options may take a value, so the real command can start at any of the first words.
        for j in range(min(len(rest), 10) + 1):
            problem = words_problem(rest[j:], depth + 1, strict=(j == 0))
            if problem:
                return problem
            if j < len(rest) and re.search(r"\s", rest[j]) and depth < MAX_DEPTH:
                # `su -c 'git push'`, `env -S 'git push'`: an option value that holds a command.
                problem = text_problem(rest[j], depth + 1)
                if problem:
                    return problem
        return None
    if not words:
        return None
    first = re.split(r"[<>]", words[0])[0] or words[0]
    if "$" in first or "*" in first or "?" in first:
        return "a command word with a variable or wildcard cannot be checked" if strict else None
    cmd, args = command_name(first), words[1:]
    if cmd in NETWORK_COMMANDS:
        return f"{cmd} is not allowed"
    if cmd in UNCHECKABLE_SHELLS:
        return f"{cmd} cannot be checked, use a normal shell command"
    if cmd == "git":
        return git_problem(args)
    if cmd in ("printenv",) or (cmd == "env" and not args) or (cmd in ("set", "export", "declare", "typeset") and not args):
        return "printing the environment can show tokens"
    if cmd == "eval":
        return text_problem(" ".join(args), depth + 1)
    if cmd in POSIX_SHELLS:
        for idx, a in enumerate(args):
            if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", a):
                text = args[idx + 1] if idx + 1 < len(args) else ""
                if len(text.strip("'\"")) == 0:
                    return f"{cmd} -c text cannot be checked"
                return text_problem(text, depth + 1)
        if all(a.startswith("-") for a in args):
            return f"{cmd} without a script or -c text reads its commands from elsewhere"
        return None
    if cmd == "find":
        for idx, a in enumerate(args):
            if a in ("-exec", "-execdir", "-ok", "-okdir"):
                inner = []
                for b in args[idx + 1:]:
                    if b in (";", "\\;", "+"):
                        break
                    inner.append(b)
                problem = words_problem(inner, depth + 1)
                if problem:
                    return problem
    return None


def split_commands(command):
    """Split on shell operators outside quotes.

    `$(` and backticks also split inside double quotes. The text up to the end of
    such a substitution is a command of its own, and after it the scan returns to
    the double-quoted string it came from (`stack` remembers that).
    """
    parts, buf, quote, i = [], [], None, 0
    stack = []  # open substitutions that started inside double quotes: ["paren", depth] or ["tick"]
    while i < len(command):
        ch = command[i]
        if quote == "'":
            buf.append(ch)
            quote = None if ch == "'" else quote
        elif quote == '"':
            if ch == "\\" and i + 1 < len(command):
                buf.append(command[i:i + 2])
                i += 1
            elif ch == "`" or command.startswith("$(", i):
                parts.append("".join(buf))
                buf, quote = [], None
                stack.append(["tick"] if ch == "`" else ["paren", 0])
                i += 1 if ch == "`" else 2
                continue
            else:
                buf.append(ch)
                quote = None if ch == '"' else quote
        elif stack and ((stack[-1][0] == "tick" and ch == "`") or (stack[-1][0] == "paren" and ch == ")" and stack[-1][1] == 0)):
            stack.pop()
            parts.append("".join(buf))
            buf, quote = [], '"'
        elif ch in "'\"":
            buf.append(ch)
            quote = ch
        elif ch == "\\" and i + 1 < len(command):
            buf.append(command[i:i + 2])
            i += 1
        elif command.startswith("$(", i):
            parts.append("".join(buf) + " $SUBST")
            buf = []
            if stack and stack[-1][0] == "paren":
                stack[-1][1] += 1
            i += 2
            continue
        elif ch == "&" and (command[i - 1:i] in ("<", ">") or command[i + 1:i + 2] == ">"):
            buf.append(ch)  # part of a redirection such as 2>&1 or &>file
        elif ch in OPERATOR_CHARS:
            if stack and stack[-1][0] == "paren":
                if ch == "(":
                    stack[-1][1] += 1
                elif ch == ")":
                    stack[-1][1] -= 1
            parts.append("".join(buf) + (" $SUBST" if ch == "`" else ""))
            buf = []
        else:
            buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def text_problem(command, depth=0):
    """Return None when the command text is allowed, otherwise the reason."""
    command = command.replace("\\\n", "").replace("\\\r\n", "")
    command = HEREDOC.sub(lambda m: " " + m.group(3), command)  # keep the rest of the line, e.g. `| sh`
    for part in split_commands(command):
        part = part.strip()
        if not part:
            continue
        try:
            words = shlex.split(part, posix=True)
        except ValueError:
            words = part.split()
        problem = words_problem(words, depth)
        if problem:
            return problem
    return None


def check_command(command):
    if SECRET_PATTERN.search(command):
        return "the command names a credential file, token or secret"
    return text_problem(command)


def check_paths(tool_input, tool=""):
    if tool in ("Write", "Edit", "NotebookEdit"):
        target = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        if isinstance(target, str) and re.search(r"(^|[\\/])\.git([\\/]|$)", target):
            return "writing inside .git could add a remote, a credential helper or a hook"
    for key in ("file_path", "path", "pattern", "glob", "notebook_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and SECRET_PATTERN.search(value):
            return "the path names a credential file or secret"
    return None


def main():
    try:
        data = json.load(sys.stdin)
        tool_input = data.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            raise ValueError
        tool = data.get("tool_name", "Bash")
        command = tool_input.get("command", "") if tool == "Bash" else ""
        if not isinstance(command, str):
            raise ValueError
    except (ValueError, AttributeError):
        print("Designer/Developer guard: could not read the tool call.", file=sys.stderr)
        return 2
    problem = check_command(command) if tool == "Bash" else check_paths(tool_input, tool)
    if problem:
        print(
            f"Blocked: the Designer/Developer must not push, use GitHub or the network ({problem}). "
            "Commit locally and tell the manager in your report.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
