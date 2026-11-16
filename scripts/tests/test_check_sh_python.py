"""Tests of the Python selection in scripts/check.sh.

They use fake executables in a temporary directory and a PATH that holds
nothing else, so they do not depend on the Pythons installed here.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BASH = shutil.which("bash")
CHECK_SH = Path(__file__).resolve().parents[1] / "check.sh"

pytestmark = pytest.mark.skipif(BASH is None, reason="bash is not available")


def _fake(bindir, name, kind):
    path = bindir / name
    if kind == "good":
        real = Path(sys.executable).as_posix()
        body = f'exec "{real}" "$@"\n'
    elif kind == "broken":
        body = "exit 9\n"
    elif kind == "nopytest":
        body = 'case "$*" in *pytest*) exit 1;; esac\nexit 0\n'
    else:
        raise ValueError(kind)
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8", newline="\n")
    path.chmod(0o755)


def _run(tmp_path, script=None, cwd=None, **fakes):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, kind in fakes.items():
        _fake(bindir, name, kind)
    # Keep the rest of the environment so the real interpreter finds its
    # packages; only PATH is replaced.
    env = dict(os.environ, PATH=bindir.as_posix(), CHECK_SH_SELECT_ONLY="1")
    return subprocess.run(
        [BASH, script or CHECK_SH.as_posix()],
        env=env, cwd=cwd, capture_output=True, text=True, timeout=60,
    )


def test_skips_stub_without_pytest_and_uses_python(tmp_path):
    r = _run(tmp_path, python3="nopytest", python="good")
    assert r.returncode == 0
    assert "using Python: python\n" in r.stdout


def test_skips_broken_python3(tmp_path):
    r = _run(tmp_path, python3="broken", py="good")
    assert r.returncode == 0
    assert "using Python: py\n" in r.stdout


def test_first_good_candidate_wins(tmp_path):
    r = _run(tmp_path, python3="good", python="good")
    assert "using Python: python3\n" in r.stdout


def test_no_pytest_anywhere_names_python_and_says_missing(tmp_path):
    r = _run(tmp_path, python3="broken", python="nopytest", py="nopytest")
    assert r.returncode == 0
    assert "using Python: python." in r.stdout + r.stderr
    assert "pytest is missing" in r.stderr


def test_no_usable_python_exits_2(tmp_path):
    r = _run(tmp_path, python3="broken")
    assert r.returncode == 2
    assert "Python was not found" in r.stderr


def test_no_python_at_all_exits_2(tmp_path):
    r = _run(tmp_path)
    assert r.returncode == 2


def test_runs_by_bare_name_from_scripts_folder(tmp_path):
    r = _run(tmp_path, script="check.sh", cwd=CHECK_SH.parent, python3="good")
    assert r.returncode == 0, r.stderr
    root_line = [l for l in r.stdout.splitlines() if "root: " in l][0]
    printed = Path(root_line.split("root: ", 1)[1].strip())
    # Git Bash prints /c/... on Windows; compare by the final folder names.
    assert printed.name == CHECK_SH.parents[1].name
