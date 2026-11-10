import random

import pytest

from countdown.layout import NUMBER_COUNT, number_at, place_numbers
from countdown.settings import MIN_GAP

WIDTH, HEIGHT, SIZE = 800, 600, 60
WINDOW_W, WINDOW_H = WIDTH, HEIGHT
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


# --- the gap between boxes

def gap_between(a, b):
    """Pixels between two boxes of side SIZE (the larger of the two axis gaps)."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1])) - SIZE


@pytest.mark.parametrize("gap", [1, 10, 25])
@pytest.mark.parametrize("seed", range(100))
def test_boxes_keep_the_gap(seed, gap):
    boxes = list(place_numbers(WIDTH, HEIGHT, SIZE, rng=random.Random(seed), gap=gap).values())
    assert len(boxes) == NUMBER_COUNT
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert gap_between(a, b) >= gap


def test_default_gap_is_zero():
    # Without a gap the old behaviour stays: the boxes may touch.
    boxes = list(make(1, width=400, height=200).values())
    assert len(boxes) == NUMBER_COUNT
    assert all(max(abs(a[0] - b[0]), abs(a[1] - b[1])) >= SIZE
               for i, a in enumerate(boxes) for b in boxes[i + 1:])


def test_gap_makes_a_tight_window_impossible():
    with pytest.raises(ValueError):
        place_numbers(300, 120, SIZE, rng=random.Random(1), gap=10)


def test_negative_gap_raises_value_error():
    with pytest.raises(ValueError):
        place_numbers(WIDTH, HEIGHT, SIZE, rng=random.Random(1), gap=-1)


def test_gap_is_kept_with_the_real_settings():
    from countdown.settings import BOX_SIZE, WINDOW_HEIGHT, WINDOW_WIDTH

    assert MIN_GAP > 0
    for seed in range(300):
        boxes = list(place_numbers(
            WINDOW_WIDTH, WINDOW_HEIGHT, BOX_SIZE, rng=random.Random(seed), gap=MIN_GAP
        ).values())
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                assert max(abs(a[0] - b[0]), abs(a[1] - b[1])) - BOX_SIZE >= MIN_GAP


# --- number_at

BOXES = {1: (100, 100), 2: (160, 100), 3: (300, 400)}  # 1 and 2 touch each other
S = 60


def test_number_at_inside_a_box():
    assert number_at(BOXES, S, 130, 130) == 1
    assert number_at(BOXES, S, 330, 430) == 3


def test_number_at_top_left_corner_is_inside():
    assert number_at(BOXES, S, 100, 100) == 1


def test_number_at_first_pixel_outside_is_not_a_hit():
    assert number_at(BOXES, S, 99, 100) is None
    assert number_at(BOXES, S, 100, 99) is None
    assert number_at(BOXES, S, 300 + S, 400) is None
    assert number_at(BOXES, S, 300, 400 + S) is None


def test_number_at_last_pixel_inside_is_a_hit():
    assert number_at(BOXES, S, 300 + S - 1, 400 + S - 1) == 3


def test_number_at_empty_background():
    assert number_at(BOXES, S, 0, 0) is None
    assert number_at(BOXES, S, 500, 300) is None


def test_number_at_touching_boxes_never_both_match():
    # Box 1 covers x 100..159, box 2 covers x 160..219.
    assert number_at(BOXES, S, 159, 120) == 1
    assert number_at(BOXES, S, 160, 120) == 2


def test_number_at_with_placed_numbers_finds_every_box_centre():
    positions = place_numbers(WINDOW_W, WINDOW_H, SIZE, rng=random.Random(5))
    for number, (x, y) in positions.items():
        assert number_at(positions, SIZE, x + SIZE // 2, y + SIZE // 2) == number
