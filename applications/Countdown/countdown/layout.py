"""Number placement for Countdown.

Decides where the numbers 1 to 10 are drawn. Pure Python: this module must
not import tkinter, so the tests can run without a display.
"""

import random

NUMBER_COUNT = 10

# Limits so an impossible layout fails with an error instead of looping forever.
_ATTEMPTS_PER_NUMBER = 200
_RESTARTS = 50


def _overlaps(a, b, size):
    """True if two square boxes of side ``size`` with top-left corners a and b overlap."""
    return abs(a[0] - b[0]) < size and abs(a[1] - b[1]) < size


def place_numbers(width, height, size, rng=None):
    """Return ``{number: (x, y)}`` for the numbers 1 to 10.

    ``(x, y)`` is the top-left corner of a square box with side ``size``.
    The boxes never overlap and lie fully inside a window of ``width`` x
    ``height``. Pass a ``random.Random`` as ``rng`` for repeatable results.

    Raises ``ValueError`` if the arguments are not positive or if the ten
    boxes cannot be placed in the window.
    """
    if width <= 0 or height <= 0 or size <= 0:
        raise ValueError("width, height and size must be positive")
    if size > width or size > height:
        raise ValueError(
            f"a box of size {size} does not fit in a window of {width} x {height}"
        )
    if rng is None:
        rng = random.Random()

    max_x = width - size
    max_y = height - size

    for _ in range(_RESTARTS):
        placed = []
        for _number in range(NUMBER_COUNT):
            for _attempt in range(_ATTEMPTS_PER_NUMBER):
                candidate = (rng.randint(0, max_x), rng.randint(0, max_y))
                if not any(_overlaps(candidate, other, size) for other in placed):
                    placed.append(candidate)
                    break
            else:
                break  # no free spot found for this number: start over
        if len(placed) == NUMBER_COUNT:
            return {number: placed[number - 1] for number in range(1, NUMBER_COUNT + 1)}

    raise ValueError(
        f"could not place {NUMBER_COUNT} boxes of size {size} "
        f"in a window of {width} x {height}"
    )


def number_at(positions, size, x, y):
    """Return the number whose box contains the point ``(x, y)``, or ``None``.

    ``positions`` is ``{number: (x, y)}`` as returned by ``place_numbers`` and
    ``size`` is the side of a box. A box covers ``px <= x < px + size`` and
    ``py <= y < py + size``, so two boxes that touch never both match.
    """
    for number, (px, py) in positions.items():
        if px <= x < px + size and py <= y < py + size:
            return number
    return None
