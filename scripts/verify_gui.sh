#!/usr/bin/env bash
# Run a Python script under a virtual display, so a tkinter window can be
# tested without a screen (for example in a cloud session).
#
# Usage:  scripts/verify_gui.sh path/to/script.py [arguments...]
# Run it from the folder the script expects (for example the project folder).
#
# Set PYTHON to choose the interpreter, for example PYTHON=/usr/bin/python3.12.
# Otherwise the first of python3, python3.13, python3.12, python3.11, python3.10
# and python that can import tkinter is used.
#
# The script only starts the script it is given. It checks nothing else.
# Exit codes: the exit code of the given script, or 2 if something is missing.

set -u

if [ "$#" -lt 1 ]; then
  echo "Usage: scripts/verify_gui.sh path/to/script.py [arguments...]" >&2
  exit 2
fi

if ! command -v xvfb-run >/dev/null 2>&1; then
  echo "verify_gui.sh: xvfb-run was not found. A virtual display is needed." >&2
  echo "  Debian/Ubuntu: sudo apt-get install xvfb" >&2
  echo "  macOS and Windows have a screen, so run the script directly instead." >&2
  exit 2
fi

py=""
if [ -n "${PYTHON:-}" ]; then
  if "$PYTHON" -c "import tkinter" >/dev/null 2>&1; then
    py="$PYTHON"
  else
    echo "verify_gui.sh: $PYTHON cannot import tkinter." >&2
    exit 2
  fi
else
  for candidate in python3 python3.13 python3.12 python3.11 python3.10 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import tkinter" >/dev/null 2>&1; then
      py="$candidate"
      break
    fi
  done
fi

if [ -z "$py" ]; then
  echo "verify_gui.sh: no Python with tkinter was found." >&2
  echo "  Debian/Ubuntu: sudo apt-get install python3-tk" >&2
  echo "  Or set PYTHON to an interpreter that has tkinter." >&2
  exit 2
fi

echo "verify_gui.sh: using $py under xvfb-run" >&2
exec xvfb-run -a "$py" "$@"
