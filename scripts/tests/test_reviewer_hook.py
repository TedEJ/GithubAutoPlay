import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "reviewer_readonly.py"
spec = importlib.util.spec_from_file_location("reviewer_readonly", HOOK)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

ALLOWED = [
    "git diff main...HEAD --stat",
    "git log --oneline -5",
    "git status",
    "git branch --list",
    "git show HEAD:WORKFLOW.md",
    "cd applications/news-reader && python -m pytest -q",
    "cd applications/news-reader && python3 -m pytest -q -k time --tb=short",
    "cd applications/news-reader && node --test",
    "scripts/check.sh applications/news-reader",
    "bash scripts/check.sh",
    "grep -rn foo . | head -20",
    "cat WORKFLOW.md",
    "python scripts/check_reviewer.py --body-file b.md --changed-files a.md",
    "ls -la 2>&1",
    "echo hi > /dev/null",
    "ls 2>/dev/null; pwd",
    "echo 'a>b'",
    "echo 'a;b'",
    "echo 'a#b'",
    "cd applications/news-reader",
    "grep -rn 'foo.*bar' applications",
    "",
]
BLOCKED = [
    "git commit -m x",
    "git push origin main",
    "git checkout -b x",
    "git branch -D x",
    "git branch newbranch",
    "git branch --set-upstream-to=x",
    "git add .",
    "git -c core.pager=x log",
    "git -C /tmp log",
    "git --git-dir=/x log",
    "git diff --output=/tmp/x",
    "git log --output=/tmp/x",
    "git diff --no-index a b",
    "git diff --ext-diff",
    "git grep -Ovim foo",
    "git cat-file --textconv HEAD:x",
    "rm -rf x",
    "echo hi > file.txt",
    "echo hi >> file.txt",
    "echo hi >&/tmp/x",
    "echo hi > /dev/null/../x",
    "cat a | tee b",
    "sed -i s/a/b/ f",
    "sed -ni p f",
    "sed -n 'w f' f",
    "awk 'BEGIN{print 1}'",
    "find . -delete",
    "find . -fls /tmp/x",
    "sort -o f f",
    "uniq a b",
    "xargs rm",
    "cat <<EOF",
    "cat < /tmp/x",
    "python -c 'open(\"x\",\"w\")'",
    "python3 script.py",
    "python -m pytest -p evil",
    "python -m pytest -c /tmp/x.ini",
    "python -m pytest --junitxml=/tmp/x",
    "python -m pytest -o cache_dir=/tmp/x",
    "node --test --import x",
    "node script.js",
    "bash -c 'rm x'",
    "scripts/check.sh --foo",
    "curl https://example.com",
    "ls && rm x",
    "ls; git push",
    "ls & touch x",
    "echo $(rm x)",
    "echo `rm x`",
    "echo $HOME",
    "cat ~/.ssh/id_rsa",
    "ls\nrm x",
    "PYTHONSTARTUP=x python -m pytest",
    "LD_PRELOAD=/tmp/x.so cat f",
    "PATH=/tmp cat f",
    "/tmp/evil/cat x",
    "./cat x",
    "{ rm x; }",
    "(rm x)",
    "git diff; git commit -m x",
    "cat a#b ; git push",
    "echo a#b > /tmp/zz",
    "ls a#; touch f",
    "echo a#b && git branch newb",
    "cd /other/checkout && scripts/check.sh",
    "python -m pytest /any/path.py",
    "python -m pytest @args.txt",
    "node --test /any/path.js",
    "scripts/check.sh ../other",
    "git log --help",
    "git log -h",
    "git log --out=x",
    "git log --outpu=x",
    "git diff --tex",
    "cat /proc/self/environ",
    "python -m pytest {/tmp/evil,x}",
    "cd {..,x} && scripts/check.sh",
    "cat /{proc,x}/self/environ",
    "cat /p*c/self/environ",
    "python -m pytest ?/x",
    "cd .[.] && scripts/check.sh",
    "cd && python -m pytest",
    "cd - && scripts/check.sh",
    "cat /etc/pass*",
]


@pytest.mark.parametrize("command", ALLOWED)
def test_allowed(command):
    assert hook.check(command) is None


@pytest.mark.parametrize("command", BLOCKED)
def test_blocked(command):
    assert hook.check(command) is not None


def run_hook(payload):
    return subprocess.run(
        [sys.executable, str(HOOK)], input=payload, capture_output=True, text=True
    )


def tool_call(command):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


def test_exit_codes():
    assert run_hook(tool_call("git status")).returncode == 0
    blocked = run_hook(tool_call("git push"))
    assert blocked.returncode == 2
    assert "read-only" in blocked.stderr


@pytest.mark.parametrize(
    "payload",
    ["not json", json.dumps({"tool_input": "x"}), json.dumps({"tool_input": {"command": 5}}), "[]"],
)
def test_unreadable_calls_are_blocked(payload):
    assert run_hook(payload).returncode == 2
