import random

import pytest

from countdown.layout import NUMBER_COUNT, place_numbers

WIDTH, HEIGHT, SIZE = 800, 600, 60
SEEDS = range(200)


def make(seed, width=WIDTH, height=HEIGHT, size=SIZE):
    return place_numbers(width, height, size, rng=random.Random(seed))


def test_returns_the_numbers_1_to_10():
    positions = make(1)
    assert sorted(positions) == list(range(1, NUMBER_COUNT + 1))


def test_ten_different_positions():
    assert len(set(make(1).values())) == NUMBER_COUNT


@pytest.mark.parametrize("seed", SEEDS)
def test_boxes_do_not_overlap(seed):
    boxes = list(make(seed).values())
    for i, (ax, ay) in enumerate(boxes):
        for bx, by in boxes[i + 1:]:
            assert abs(ax - bx) >= SIZE or abs(ay - by) >= SIZE


@pytest.mark.parametrize("seed", SEEDS)
def test_boxes_are_fully_inside_the_window(seed):
    for x, y in make(seed).values():
        assert 0 <= x and x + SIZE <= WIDTH
        assert 0 <= y and y + SIZE <= HEIGHT


def test_same_seed_gives_same_result():
    assert make(7) == make(7)


def test_different_seeds_give_different_results():
    assert len({tuple(sorted(make(seed).items())) for seed in range(20)}) > 1


def test_works_without_rng():
    assert len(place_numbers(WIDTH, HEIGHT, SIZE)) == NUMBER_COUNT


def test_tight_window_still_works():
    # A small window with room for 18 boxes: ten must still fit.
    assert len(make(3, width=400, height=200, size=60)) == NUMBER_COUNT


@pytest.mark.parametrize(
    "width, height, size",
    [
        (100, 100, 60),   # ten boxes cannot fit
        (50, 600, 60),    # box wider than the window
        (800, 50, 60),    # box taller than the window
        (0, 600, 60),
        (800, 600, 0),
        (800, -1, 60),
    ],
)
def test_impossible_window_raises_value_error(width, height, size):
    with pytest.raises(ValueError):
        place_numbers(width, height, size, rng=random.Random(0))
