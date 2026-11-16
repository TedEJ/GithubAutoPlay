#!/bin/sh
# Fail-closed wrapper for designer_guard.py.
#
# Claude Code treats a hook that exits with a code other than 0 or 2 as a
# non-blocking error and lets the tool call run. If Python is missing (on
# Windows the command is often `python` or `py`, not `python3`) the check would
# therefore be skipped silently. This wrapper tries each Python name in turn and
# blocks the call (exit 2) when none of them gives a real answer (0 or 2).
case "$0" in
  */*) dir="${0%/*}" ;;
  *\\*) dir="${0%\\*}" ;;
  *) dir="." ;;
esac
input=$(cat)
for py in python3 python py; do
  if command -v "$py" >/dev/null 2>&1; then
    printf '%s' "$input" | "$py" "$dir/designer_guard.py"
    rc=$?
    if [ "$rc" -eq 0 ] || [ "$rc" -eq 2 ]; then
      exit "$rc"
    fi
  fi
done
echo "Blocked: the Designer/Developer guard could not run (no working Python found)." >&2
exit 2
