import importlib.util
import json
import os
import shutil
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
    result = run_wrapper(tmp_path, "git status", {"python3": None, "python": None})
    assert result.returncode == 2


@needs_sh
def test_wrapper_falls_back_to_the_next_python(tmp_path):
    result = run_wrapper(tmp_path, "git status", {"python3": None, "python": sys.executable})
    assert result.returncode == 0


@needs_sh
def test_wrapper_does_not_fall_through_after_a_block(tmp_path):
    # The first interpreter says "block" (2); a later one must not be asked.
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


def test_reviewer_agent_uses_the_wrapper():
    text = (HOOK.parents[1] / "agents" / "reviewer.md").read_text(encoding="utf-8")
    assert "reviewer_readonly.sh" in text
    assert "python3 " not in text.split("command:")[1].splitlines()[0]


# --- paths inside the repository (issue #121) ---------------------------------------


@pytest.fixture()
def tree(tmp_path):
    repo = tmp_path / "repo"
    (repo / "applications" / "news-reader" / "tests").mkdir(parents=True)
    (repo / "scripts").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (repo / "link").symlink_to(outside, target_is_directory=True)
    except OSError:  # no symlink privilege (Windows)
        pass
    return repo, outside, tmp_path / "repo-evil"


def posix(command):
    """Paths in test commands use forward slashes: like bash, the hook drops unquoted backslashes."""
    return command.replace("\\", "/")


def verdict(command, root, cwd=None):
    return hook.check(posix(command), hook.Context(root=str(root), cwd=str(cwd or root)))


def test_absolute_paths_inside_the_repository_are_allowed(tree):
    repo = tree[0]
    sub = repo / "applications" / "news-reader"
    for command in [
        f"cd {repo}",
        f"cd {sub} && python -m pytest -q",
        f"python -m pytest {sub}/tests -q",
        f"python3 -m pytest {sub}/tests/test_x.py::test_name -q",
        f"node --test {sub}",
        f"bash {repo}/scripts/check.sh",
        f"sh {repo}/scripts/check.sh applications/news-reader",
        f"{repo}/scripts/check.sh applications/news-reader",
        f"python {repo}/scripts/check_reviewer.py --body-file b.md --changed-files c.txt",
        "cd applications/news-reader",
        "cd applications/../applications",
    ]:
        assert verdict(command, repo) is None, command


def test_git_dash_c_inside_the_repository_is_allowed(tree):
    repo = tree[0]
    for command in [
        f"git -C {repo} status",
        f"git -C {repo}/applications log --oneline -3",
        "git -C applications diff main...HEAD --stat",
        f"git -C {repo} show HEAD:WORKFLOW.md",
    ]:
        assert verdict(command, repo) is None, command


def test_relative_paths_follow_the_working_directory(tree):
    repo = tree[0]
    sub = repo / "applications" / "news-reader"
    for command in [
        "python -m pytest -q",
        "../../scripts/check.sh",
        "cd ../.. && scripts/check.sh",
        "cd ../.. && git status",
        "bash ../../scripts/check.sh",
        "python -m pytest ../../applications/news-reader/tests",
    ]:
        assert verdict(command, repo, sub) is None, command
    # From a sub folder the plain relative name is not the repository's script.
    assert verdict("scripts/check.sh", repo, sub) is not None
    assert verdict("bash scripts/check.sh", repo, sub) is not None
    assert verdict("cd ../../.. && git status", repo, sub) is not None  # leaves the repository
    assert verdict("cd ../../.. && python -m pytest", repo, sub) is not None


def test_safe_python_options_are_allowed(tree):
    repo = tree[0]
    for command in [
        "python -W error -m pytest -q",
        "python -Werror -m pytest -q",
        "python -W ignore -m pytest",
        "python -W error::DeprecationWarning -m pytest",
        "python3 -X utf8 -m pytest",
        "python -X dev -W error -m pytest -q",
    ]:
        assert verdict(command, repo) is None, command


def test_paths_outside_the_repository_are_blocked(tree):
    repo, outside, evil = tree
    for command in [
        f"cd {outside}",
        f"cd {evil}",
        f"cd {repo}-evil",
        f"cd {repo}/..",
        f"cd {repo}/applications/../..",
        "cd ..",
        "cd applications/../..",
        "cd /tmp",
        f"python -m pytest {outside}",
        f"python -m pytest {evil}/test_x.py",
        "python -m pytest ../outside",
        f"node --test {outside}",
        f"bash {outside}/check.sh",
        f"{outside}/scripts/check.sh",
        f"{evil}/scripts/check.sh",
        f"python {outside}/scripts/check_reviewer.py",
        f"git -C {outside} status",
        f"git -C {evil} status",
        "git -C .. log",
        "git -C /tmp log",
        "git -C ~ log",
        f"cd {repo}/applications && git -C ../.. status && git -C ../../.. log",
        "git -C",
        f"git -C {repo}",
        f"git -C {repo} commit -m x",
        f"git -C {repo} -c core.pager=x log",
        f"git -C {repo} -C /tmp log",
        f"git -C {repo} --git-dir=/x log",
        f"git -C {repo} --work-tree=/x log",
        f"git -C {repo} --exec-path=/x log",
        f"git -C {repo}/* log",
        f"cd {repo}/*",
        f"cd {repo}/applications ; cd ../.. ; cd ..",
    ]:
        assert verdict(command, repo) is not None, command


def test_a_symlink_pointing_out_of_the_repository_is_blocked(tree):
    repo, outside, _ = tree
    if not (repo / "link").is_symlink():
        pytest.skip("symlinks are not available")
    for command in [
        "cd link",
        f"cd {repo}/link",
        "python -m pytest link/test_x.py",
        f"python -m pytest {repo}/link",
        "node --test link",
        "git -C link status",
        f"git -C {repo}/link status",
        "bash link/check.sh",
    ]:
        assert verdict(command, repo) is not None, command


def test_unsafe_python_options_are_still_blocked(tree):
    repo = tree[0]
    for command in [
        "python -W -m pytest",
        "python -W bogus -m pytest",
        "python -W ignore:message -m pytest",
        "python -W error",
        "python -X importtime -m pytest",
        "python -X pycache_prefix=/tmp/x -m pytest",
        "python -X",
        "python -W error script.py",
        "python -W error -c 'pass'",
        "python -m pytest -W error",
        "python -B -m pytest",
        "python -u -m pytest",
    ]:
        assert verdict(command, repo) is not None, command


WIN_ROOT = "C:\\Users\\me\\repo"


def test_windows_paths_are_compared_with_the_repository(tree):
    repo = tree[0]
    for root in (WIN_ROOT, "C:/Users/me/repo", "/c/Users/me/repo"):
        ctx = lambda: hook.Context(root=root, cwd=root)  # noqa: E731 - a fresh context per command
        for command in [
            "cd C:/Users/me/repo",
            "cd C:/Users/me/repo/applications/news-reader",
            "cd /c/Users/me/repo/applications",
            "cd 'C:\\Users\\me\\repo\\applications'",
            "cd c:/users/ME/Repo/applications",
            "cd applications && python -m pytest",
            "python -m pytest C:/Users/me/repo/applications/tests -q",
            "git -C C:/Users/me/repo status",
            "git -C /c/Users/me/repo/applications log",
            "bash C:/Users/me/repo/scripts/check.sh",
            "C:/Users/me/repo/scripts/check.sh",
        ]:
            assert hook.check(command, ctx()) is None, (root, command)
        for command in [
            "cd C:/Users/other/repo",
            "cd C:/Users/me/repo-evil",
            "cd C:/Users/me/repo/..",
            "cd C:/Users/me/repo/../other",
            "cd D:/Users/me/repo",
            "cd /c/Users/me/repo-evil",
            "cd /c/Users/me",
            "cd /d/Users/me/repo",
            "cd C:/Users/me/repo/*",
            "cd C:/Users/me/repo/applications/../../..",
            "python -m pytest C:/Users/other",
            "python -m pytest C:/Windows/System32",
            "git -C C:/Users/other/repo status",
            "git -C C:/Users/me log",
            "bash C:/Users/other/scripts/check.sh",
            "node --test D:/x",
            "cd /tmp",
            "git -C /tmp log",
        ]:
            assert hook.check(command, ctx()) is not None, (root, command)


def test_a_windows_style_path_is_not_inside_a_posix_repository(tree):
    repo = tree[0]
    assert verdict("cd C:/Users/me/repo", repo) is not None
    assert hook.check("cd /home/x/repo", hook.Context(root=WIN_ROOT, cwd=WIN_ROOT)) is not None


def run_hook_in(root, cwd, command):
    payload = json.dumps({"tool_name": "Bash", "cwd": str(cwd), "tool_input": {"command": posix(command)}})
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root)}
    return subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, env=env)


def test_the_hook_reads_cwd_and_the_project_directory(tree):
    repo = tree[0]
    sub = repo / "applications" / "news-reader"
    assert run_hook_in(repo, sub, "cd ../.. && git status").returncode == 0
    assert run_hook_in(repo, sub, "cd ../../.. && python -m pytest").returncode == 2
    assert run_hook_in(repo, repo, f"git -C {repo} status").returncode == 0
    assert run_hook_in(repo, repo, "git -C /tmp status").returncode == 2
    assert run_hook_in(repo, repo, f"cd {tree[1]}").returncode == 2
    # a working directory outside the repository makes relative paths resolve outside it
    assert run_hook_in(repo, tree[1], "python -m pytest tests").returncode == 2
    assert run_hook_in(repo, tree[1], "cd ../repo && python -m pytest").returncode == 0


def test_the_project_directory_defaults_to_the_repository_of_the_hook():
    root = HOOK.parents[2]
    payload = json.dumps({"tool_name": "Bash", "cwd": str(root), "tool_input": {"command": "cd scripts && python -m pytest tests -q"}})
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    result = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, env=env)
    assert result.returncode == 0


# --- review round 1 of issue #121 ---------------------------------------------------


def test_cd_is_tracked_only_where_the_shell_certainly_changes_folder(tree):
    repo = tree[0]
    for command in [
        "cd applications | node --test ..",
        "cd applications | git -C .. status",
        "cd applications | bash ../scripts/check.sh",
        "cd nonexistent ; node --test applications/../..",
        "cd applications/news-reader ; python -m pytest ../..",
        "cd applications || python -m pytest ..",
        "true || cd applications && node --test ..",
        "ls | cd applications && node --test ..",
        "cd applications && ls ; python -m pytest ..",
        "cd applications && ls || python -m pytest ..",
        "cd applications; cd ../..",
    ]:
        assert verdict(command, repo) is not None, command
    for command in [
        "cd applications && ls | head -3",
        "ls ; cd applications && python -m pytest -q",
        "cd applications && cd news-reader && python -m pytest -q",
        "cd applications && git status | head",
    ]:
        assert verdict(command, repo) is None, command


def test_dot_dot_after_a_symlink_is_resolved_through_the_link(tree):
    repo, outside, _ = tree
    if not (repo / "link").is_symlink():
        pytest.skip("symlinks are not available")
    for command in [
        "cd link/..",
        f"cd {repo}/link/..",
        "python -m pytest link/..",
        "git -C link/.. status",
        "node --test link/../applications",
        "cd link && python -m pytest ..",
    ]:
        assert verdict(command, repo) is not None, command
    # a link that stays inside the repository is fine, and `..` goes up from its target
    (repo / "applications" / "inner").symlink_to(repo / "applications" / "news-reader", target_is_directory=True)
    assert verdict("cd applications/inner && python -m pytest -q", repo) is None
    assert verdict("cd applications/inner && python -m pytest ../../..", repo) is not None


def test_the_repository_may_be_reached_through_a_symlink(tree, tmp_path):
    repo = tree[0]
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(repo, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available")
    assert verdict(f"cd {repo}/applications", alias) is None
    assert verdict(f"git -C {alias} status", repo) is None
    assert verdict(f"git -C {alias}/.. status", repo) is not None


def test_windows_names_with_trailing_dots_or_spaces_are_refused():
    ctx = lambda: hook.Context(root=WIN_ROOT, cwd=WIN_ROOT)  # noqa: E731
    for command in [
        "cd 'C:/Users/me/repo/.. '",
        "cd 'C:/Users/me/repo/sub.'",
        "cd 'C:/Users/me/repo/a. /b'",
        "cd 'C:/Users/me/repo/. .'",
    ]:
        assert hook.check(command, ctx()) is not None, command
    assert hook.check("cd C:/Users/me/repo/sub", ctx()) is None


def test_pytest_node_ids_are_checked_by_their_file_part(tree):
    repo = tree[0]
    assert verdict(f"python -m pytest {repo}/applications/news-reader/tests/test_x.py::test_a -q", repo) is None
    assert verdict("python -m pytest /etc/passwd::x", repo) is not None
    assert verdict("python -m pytest ../x.py::test", repo) is not None


@pytest.mark.skipif(sys.platform == "win32", reason="a lone surrogate is a valid file name on Windows")
def test_a_path_that_cannot_be_encoded_blocks_instead_of_crashing(tree):
    repo = tree[0]
    payload = json.dumps({"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command": 'cd "\ud800"'}})
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo)}
    result = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, env=env)
    assert result.returncode == 2
