"""Texts shown in the Countdown window. Pure Python, no tkinter."""

from countdown.game import ALLOWED_DELAYS


def lose_message(correct_count):
    """The text of the lose screen: how many numbers were clicked correctly."""
    noun = "number" if correct_count == 1 else "numbers"
    return f"You lost. You clicked {correct_count} {noun} correctly."


def delay_label(seconds):
    """The text of a start screen button, e.g. "1 second" or "5 seconds"."""
    if seconds not in ALLOWED_DELAYS:
        raise ValueError(f"delay must be one of {ALLOWED_DELAYS}, got {seconds!r}")
    noun = "second" if seconds == 1 else "seconds"
    return f"{seconds} {noun}"
