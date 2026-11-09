import random

import pytest

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


def test_new_game_default_delay_is_five_seconds():
    assert new_game().delay_seconds == 5


@pytest.mark.parametrize("delay", [1, 5, 10])
def test_new_game_uses_the_given_delay(delay):
    game = new_game(delay_seconds=delay)
    assert game.delay_seconds == delay
    assert game.delay_milliseconds == delay * 1000


@pytest.mark.parametrize("delay", [0, 2, 15, None])
def test_new_game_with_an_invalid_delay_raises_value_error(delay):
    with pytest.raises(ValueError):
        new_game(delay_seconds=delay)


def test_restart_keeps_the_delay_but_makes_a_new_game():
    first = new_game(rng=random.Random(1), delay_seconds=10)
    second = new_game(rng=random.Random(2), delay_seconds=first.delay_seconds)
    assert second is not first
    assert second.delay_seconds == 10
    assert second.phase is Phase.SHOWING
    assert second.positions != first.positions
