"""Game state for Countdown.

The rules of one round (rules 3 to 8 in the README) as a small state machine.
It knows nothing about windows or timers: the GUI calls ``hide()`` when its
timer ends and ``click()`` when the player clicks a number. Pure Python: this
module must not import tkinter, so the tests can run without a display.
"""

from enum import Enum
from types import MappingProxyType

ALLOWED_DELAYS = (1, 5, 10)
NUMBER_COUNT = 10


def delay_to_milliseconds(delay_seconds):
    """Convert a delay in seconds to whole milliseconds."""
    return int(delay_seconds * 1000)


class Phase(Enum):
    SHOWING = "showing"  # numbers are visible, waiting for the timer
    PLAYING = "playing"  # numbers are hidden (X), the player clicks them
    LOST = "lost"
    WON = "won"


class Game:
    """One round of Countdown. A new round is a new ``Game`` object."""

    def __init__(self, positions, delay_seconds):
        if delay_seconds not in ALLOWED_DELAYS:
            allowed = ", ".join(str(d) for d in ALLOWED_DELAYS)
            raise ValueError(f"delay_seconds must be one of {allowed}, got {delay_seconds!r}")
        if sorted(positions) != list(range(1, NUMBER_COUNT + 1)):
            raise ValueError("positions must have exactly the numbers 1 to 10")
        self._positions = MappingProxyType(dict(positions))
        self._delay_seconds = delay_seconds
        self._phase = Phase.SHOWING
        self._found = []

    @property
    def phase(self):
        return self._phase

    @property
    def positions(self):
        """Read-only ``{number: (x, y)}``. The positions never change in a round."""
        return self._positions

    @property
    def delay_seconds(self):
        return self._delay_seconds

    @property
    def delay_milliseconds(self):
        """The delay in milliseconds, for a GUI timer."""
        return delay_to_milliseconds(self._delay_seconds)

    @property
    def numbers_visible(self):
        """True if the numbers are drawn, False if every number is shown as an X.

        Only the playing phase hides them (rule 3). After a loss all numbers are
        shown again (rule 7).
        """
        return self._phase is not Phase.PLAYING

    @property
    def next_number(self):
        """The number the player must click next, or ``None`` after a win."""
        if self._phase is Phase.WON:
            return None
        return len(self._found) + 1

    @property
    def found(self):
        """The numbers clicked correctly so far, in order."""
        return tuple(self._found)

    @property
    def correct_count(self):
        """How many numbers were clicked correctly (before a mistake, or in total)."""
        return len(self._found)

    def hide(self):
        """End the showing phase: the numbers turn into X. Only valid in SHOWING."""
        if self._phase is not Phase.SHOWING:
            raise ValueError(f"cannot hide in phase {self._phase.name}")
        self._phase = Phase.PLAYING

    def click(self, number):
        """The player clicked the X of ``number``. Only valid in PLAYING.

        The next number in order is marked as found (the tenth wins the game).
        Any other number, including one that was already found, loses at once.
        """
        if self._phase is not Phase.PLAYING:
            raise ValueError(f"cannot click in phase {self._phase.name}")
        if number not in self._positions:
            raise ValueError(f"unknown number: {number!r}")
        if number != self.next_number:
            self._phase = Phase.LOST
            return
        self._found.append(number)
        if len(self._found) == NUMBER_COUNT:
            self._phase = Phase.WON
