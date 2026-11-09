"""Texts shown in the Countdown window. Pure Python, no tkinter."""


def lose_message(correct_count):
    """The text of the lose screen: how many numbers were clicked correctly."""
    noun = "number" if correct_count == 1 else "numbers"
    return f"You lost. You clicked {correct_count} {noun} correctly."
