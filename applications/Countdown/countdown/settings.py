"""Settings and the start of a round for Countdown.

Kept apart from the GUI so it can be tested without ``tkinter`` or a display.
"""

from countdown.game import Game
from countdown.layout import place_numbers

WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
BOX_SIZE = 60
DEFAULT_DELAY_SECONDS = 5


def new_game(rng=None):
    """Start a new round: place the numbers and create the ``Game``."""
    positions = place_numbers(WINDOW_WIDTH, WINDOW_HEIGHT, BOX_SIZE, rng=rng)
    return Game(positions, DEFAULT_DELAY_SECONDS)
