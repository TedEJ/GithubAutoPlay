import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "designer_guard.py"
spec = importlib.util.spec_from_file_location("designer_guard", HOOK)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

ALLOWED = [
    "git status",
    "git add .",
    "git commit -m 'Add the guard'",
    "git commit -m 'Block git push and gh'",
    'git commit -m "no (git push) here; no gh either"',
    "git commit -m \"$(cat <<'EOF'\nBlock git push\ngh pr create\nEOF\n)\"",
    "git checkout -b designer-guard",
    "git switch main && git pull --ff-only",
    "git fetch origin main",
    "git log --oneline -5",
    "git diff main...HEAD --stat",
    "git stash && git stash pop",
    "git remote -v",
    "git config --get user.name",
    "git config --list",
    "git worktree add ../wt -b x",
    "python -m pytest -q",
    "python3 -m pytest scripts/tests -q",
    "scripts/check.sh applications/news-reader",
    "bash scripts/check.sh",
    "cd applications/news-reader && python -m pytest",
    "node --test",
    "python -m pip install -r requirements.txt",
    "grep -rn 'git push' WORKFLOW.md",
    "cat WORKFLOW.md | head -20",
    "echo 'a;b' > notes.txt",
    "ls 2>&1",
    "mkdir -p x && touch x/y.py",
    "",
]
BLOCKED = [
    # git push in every common form
    "git push",
    "git push origin main",
    "git push -u origin my-branch",
    "git push --force origin my-branch",
    "git push https://github.com/TedEJ/GithubAutoPlay.git HEAD",
    "git -C . push",
    "git -C /tmp/x push",
    "git --git-dir=.git push",
    "git --no-pager push",
    "git -c x=y push",
    "git -cx=y push",
    "git -c http.extraheader=x commit",
    "git --config-env=a=B status",
    "GIT_TRACE=1 git push",
    "git  push",
    "git\tpush",
    "'git' push",
    '"git" "push"',
    "git 'push'",
    "/usr/bin/git push",
    "git.exe push",
    "GIT push",
    "git send-pack origin x",
    "git credential fill",
    "git credential-manager get",
    # remotes and configuration
    "git remote add origin https://example.com/x.git",
    "git remote set-url origin https://example.com/x.git",
    "git remote remove origin",
    "git config user.name x",
    "git config --global credential.helper store",
    "git config --get credential.helper",
    "git config --get remote.origin.url",
    "git config --unset remote.origin.url",
    "git config alias.p push",
    # GitHub and network commands
    "gh pr create",
    "gh issue close 1",
    "gh api repos/x/y",
    "gh",
    "curl https://example.com",
    "curl -X POST -d x https://api.github.com",
    "wget https://example.com/x",
    "Invoke-WebRequest https://example.com",
    "iwr https://example.com",
    "Invoke-RestMethod https://example.com",
    "irm https://example.com",
    "ssh git@github.com",
    "scp x host:y",
    "rsync -a x host:y",
    "nc example.com 80",
    "telnet example.com 80",
    "certutil -urlcache -f https://example.com x",
    "powershell -Command git push",
    "pwsh -c 'git push'",
    "cmd /c git push",
    # chaining, substitution, quoting and wrappers
    "git status && git push",
    "git status; git push",
    "git status || git push",
    "git status | git push",
    "git status & git push",
    "git status\ngit push",
    "(git push)",
    "{ git push; }",
    "echo $(git push)",
    "echo `git push`",
    'echo "$(git push)"',
    'echo "`gh pr list`"',
    "echo x && (cd . && curl https://example.com)",
    "bash -c 'git push'",
    'sh -c "gh pr create"',
    "bash -lc 'git push'",
    "eval git push",
    "eval 'curl https://example.com'",
    "env FOO=1 git push",
    "env -u X git push",
    "sudo git push",
    "time git push",
    "nohup git push",
    "timeout 30 git push",
    "command git push",
    "exec git push",
    "xargs git push",
    "echo x | xargs gh pr create",
    "find . -exec git push \\;",
    "find . -name x -exec curl https://example.com {} +",
    "FOO=bar curl https://example.com",
    "$CMD push",
    "g* push",
    # credentials and secrets
    "cat ~/.git-credentials",
    "cat .netrc",
    "cat ~/.ssh/id_rsa",
    "ls ~/.ssh",
    "cat .env",
    "cat applications/x/.env.local",
    "cat ~/.config/gh/hosts.yml",
    "cat ~/.aws/credentials",
    "cat ~/.npmrc",
    "grep -r github_pat_ .",
    "echo ghp_abcdefghijklmnop",
    "echo $GITHUB_TOKEN",
    "echo $GH_TOKEN",
    "printenv",
    "printenv GITHUB_TOKEN",
    "env",
    "set",
    "cat /root/.claude/projects/x/session.jsonl",
    "git credential approve",
]


@pytest.mark.parametrize("command", ALLOWED)
def test_allowed(command):
    assert guard.check_command(command) is None


@pytest.mark.parametrize("command", BLOCKED)
def test_blocked(command):
    assert guard.check_command(command) is not None


def test_deeply_nested_commands_are_blocked():
    command = "git push"
    for _ in range(guard.MAX_DEPTH + 2):
        command = "bash -c " + json.dumps(command)
    assert guard.check_command(command) is not None


def run_hook(payload):
    return subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True)


def tool_call(command, tool="Bash"):
    return json.dumps({"tool_name": tool, "tool_input": {"command": command}})


def test_exit_codes_and_message():
    assert run_hook(tool_call("git status")).returncode == 0
    blocked = run_hook(tool_call("git push origin main"))
    assert blocked.returncode == 2
    assert "must not push" in blocked.stderr
    assert "report" in blocked.stderr


@pytest.mark.parametrize(
    "payload",
    ["not json", "", "[]", json.dumps({"tool_input": "x"}), json.dumps({"tool_input": {"command": 5}})],
)
def test_unreadable_calls_are_blocked(payload):
    assert run_hook(payload).returncode == 2


@pytest.mark.parametrize(
    "tool, key, value, expected",
    [
        ("Read", "file_path", "WORKFLOW.md", 0),
        ("Read", "file_path", "scripts/check.sh", 0),
        ("Grep", "pattern", "def main", 0),
        ("Glob", "pattern", "**/*.py", 0),
        ("Read", "file_path", "/home/me/.git-credentials", 2),
        ("Read", "file_path", "C:\\Users\\me\\.ssh\\id_ed25519", 2),
        ("Read", "file_path", "/home/me/.config/gh/hosts.yml", 2),
        ("Read", "file_path", "applications/x/.env", 2),
        ("Grep", "path", "/home/me/.aws", 2),
        ("Grep", "pattern", "github_pat_[A-Za-z0-9_]+", 2),
        ("Glob", "pattern", "**/.netrc", 2),
    ],
)
def test_file_tools_may_not_read_credentials(tool, key, value, expected):
    payload = json.dumps({"tool_name": tool, "tool_input": {key: value}})
    assert run_hook(payload).returncode == expected


WRAPPER = HOOK.with_suffix(".sh")
SH = shutil.which("sh")
needs_sh = pytest.mark.skipif(
    SH is None or sys.platform == "win32", reason="needs a POSIX sh and symlinks"
)


def run_wrapper(tmp_path, command, interpreters):
    """Run the wrapper with a PATH that holds only `cat` and the given interpreters."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "cat").symlink_to(shutil.which("cat"))
    for name, target in interpreters.items():
        if target is None:
            (bin_dir / name).write_text("#!/bin/sh\nexit 9\n")
            (bin_dir / name).chmod(0o755)
        else:
            (bin_dir / name).symlink_to(target)
    return subprocess.run(
        [SH, str(WRAPPER)],
        input=tool_call(command),
        capture_output=True,
        text=True,
        env={"PATH": str(bin_dir)},
    )


@needs_sh
def test_wrapper_passes_through_allow_and_block(tmp_path):
    py = {"python3": sys.executable}
    assert run_wrapper(tmp_path / "a", "git status", py).returncode == 0
    assert run_wrapper(tmp_path / "b", "git push", py).returncode == 2


@needs_sh
def test_wrapper_blocks_when_no_python_exists(tmp_path):
    result = run_wrapper(tmp_path, "git status", {})
    assert result.returncode == 2
    assert "could not run" in result.stderr


@needs_sh
def test_wrapper_blocks_when_python_is_broken(tmp_path):
    assert run_wrapper(tmp_path, "git status", {"python3": None, "python": None}).returncode == 2


@needs_sh
def test_wrapper_falls_back_to_the_next_python(tmp_path):
    assert run_wrapper(tmp_path, "git status", {"python3": None, "python": sys.executable}).returncode == 0


@needs_sh
def test_wrapper_does_not_fall_through_after_a_block(tmp_path):
    first = tmp_path / "first.sh"
    first.write_text("#!/bin/sh\nexit 2\n")
    first.chmod(0o755)
    result = run_wrapper(tmp_path, "git status", {"python3": str(first), "python": sys.executable})
    assert result.returncode == 2


@needs_sh
def test_wrapper_blocks_empty_input(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "cat").symlink_to(shutil.which("cat"))
    (bin_dir / "python3").symlink_to(sys.executable)
    result = subprocess.run(
        [SH, str(WRAPPER)], input="", capture_output=True, text=True, env={"PATH": str(bin_dir)}
    )
    assert result.returncode == 2


@needs_sh
def test_wrapper_works_from_any_directory_and_with_a_bare_name(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "cat").symlink_to(shutil.which("cat"))
    (bin_dir / "python3").symlink_to(sys.executable)
    for args, cwd in (([SH, str(WRAPPER)], tmp_path), ([SH, WRAPPER.name], WRAPPER.parent)):
        result = subprocess.run(
            args, input=tool_call("git status"), capture_output=True, text=True,
            env={"PATH": str(bin_dir)}, cwd=cwd,
        )
        assert result.returncode == 0, args


def test_designer_agent_uses_the_wrapper_for_bash_and_file_tools():
    text = (HOOK.parents[1] / "agents" / "designer-developer.md").read_text(encoding="utf-8")
    assert "designer_guard.sh" in text
    assert "python3 " not in text.split("command:")[1].splitlines()[0]
    matcher = text.split("matcher:")[1].splitlines()[0]
    for tool in ("Bash", "Read", "Grep", "Glob"):
        assert tool in matcher
