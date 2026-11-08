"""Entry point: run the game with ``python -m countdown``."""

import sys


def main() -> int:
    """Start Countdown. Returns the exit code (0 means success)."""
    # Imported here so that importing the package never needs tkinter or a display.
    try:
        from countdown import gui
    except ImportError:
        print(
            "Countdown needs tkinter, which is not installed. "
            "On some Linux systems it is a separate package (python3-tk)."
        )
        return 1
    return gui.run()


if __name__ == "__main__":
    sys.exit(main())
