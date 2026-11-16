#!/usr/bin/env bash
# Run the same kind of checks as the required check `checks` (see
# .github/workflows/ci.yml), locally, before a pull request is created.
#
# Usage:  scripts/check.sh [project folder]
# Default project folder: applications/Countdown
#
# Steps: required files, relative links in the Markdown files of the repository
# root, the tests of the project folder, and the tests of the scripts.
# Exits with 0 when every step passes and 1 when any step fails.
#
# The link check below repeats the logic in ci.yml. If one of them changes,
# change the other as well, so they keep giving the same answer.

set -u

root="$(cd "${BASH_SOURCE[0]%/*}/.." && pwd)"
project="${1:-applications/Countdown}"
# A project folder is relative to the repository root, unless it is absolute.
case "$project" in
  /*) project_dir="$project" ;;
  *) project_dir="$root/$project" ;;
esac

py=""
first_running=""
for candidate in python3 python py; do
  command -v "$candidate" >/dev/null 2>&1 || continue
  "$candidate" -c "import sys" >/dev/null 2>&1 || continue
  [ -n "$first_running" ] || first_running="$candidate"
  if "$candidate" -c "import pytest" >/dev/null 2>&1; then
    py="$candidate"
    break
  fi
done
if [ -n "$py" ]; then
  echo "check.sh: using Python: $py"
elif [ -n "$first_running" ]; then
  py="$first_running"
  echo "check.sh: using Python: $py. pytest is missing in it (no candidate could import pytest), so the test steps will fail. Install it with: $py -m pip install pytest" >&2
else
  echo "check.sh: Python was not found (tried python3, python, py). Install Python 3.10 or newer." >&2
  exit 2
fi
[ -z "${CHECK_SH_SELECT_ONLY:-}" ] || exit 0

if [ ! -d "$project_dir" ]; then
  echo "check.sh: project folder not found: $project" >&2
  exit 2
fi

results=()
failed=0

record() { # name, exit code
  if [ "$2" -eq 0 ]; then
    results+=("PASS  $1")
  else
    results+=("FAIL  $1")
    failed=1
  fi
}

echo "== Required files exist and are not empty"
missing=0
for f in README.md WORKFLOW.md CLAUDE.md LICENSE; do
  if [ ! -s "$root/$f" ]; then
    echo "Required file is missing or empty: $f"
    missing=1
  fi
done
record "required files" "$missing"

echo "== Relative links in Markdown files resolve"
(cd "$root" && "$py" - <<'PY'
import pathlib, re, sys
bad = 0
link = re.compile(r'\[[^\]]*\]\(([^)\s]+)\)')
for md in pathlib.Path('.').glob('*.md'):
    for target in link.findall(md.read_text(encoding='utf-8')):
        if re.match(r'^(https?:|mailto:|#)', target):
            continue
        path = target.split('#')[0]
        if path and not (md.parent / path).exists():
            print(f"Broken link in {md}: {target}")
            bad = 1
sys.exit(bad)
PY
)
record "links in root Markdown files" "$?"

echo "== Tests in $project"
(cd "$project_dir" && "$py" -m pytest -q)
record "tests in $project" "$?"

echo "== Tests of the scripts"
if [ -d "$root/scripts/tests" ]; then
  (cd "$root/scripts" && "$py" -m pytest -q tests)
  record "tests of the scripts" "$?"
fi

echo
echo "== Summary"
printf '%s\n' "${results[@]}"
if [ "$failed" -ne 0 ]; then
  echo "check.sh: at least one step FAILED"
  exit 1
fi
echo "check.sh: all steps passed"
