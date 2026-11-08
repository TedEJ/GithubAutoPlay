import random

from countdown.game import Game, Phase
from countdown.settings import (
    BOX_SIZE,
    DEFAULT_DELAY_SECONDS,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    new_game,
)


def test_new_game_starts_showing_with_the_default_delay():
    game = new_game(rng=random.Random(1))
    assert isinstance(game, Game)
    assert game.phase is Phase.SHOWING
    assert game.delay_seconds == DEFAULT_DELAY_SECONDS == 5


def test_new_game_places_ten_numbers_inside_the_window():
    for seed in range(50):
        positions = new_game(rng=random.Random(seed)).positions
        assert sorted(positions) == list(range(1, 11))
        for x, y in positions.values():
            assert 0 <= x and x + BOX_SIZE <= WINDOW_WIDTH
            assert 0 <= y and y + BOX_SIZE <= WINDOW_HEIGHT


def test_new_game_without_rng_works():
    assert new_game().phase is Phase.SHOWING
