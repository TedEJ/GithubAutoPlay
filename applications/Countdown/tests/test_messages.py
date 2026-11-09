import pytest

from countdown.game import ALLOWED_DELAYS
from countdown.messages import delay_label, lose_message, win_message


@pytest.mark.parametrize(
    "count, text",
    [
        (0, "You lost. You clicked 0 numbers correctly."),
        (1, "You lost. You clicked 1 number correctly."),
        (2, "You lost. You clicked 2 numbers correctly."),
        (10, "You lost. You clicked 10 numbers correctly."),
    ],
)
def test_lose_message(count, text):
    assert lose_message(count) == text


@pytest.mark.parametrize(
    "seconds, text",
    [(1, "1 second"), (5, "5 seconds"), (10, "10 seconds")],
)
def test_delay_label(seconds, text):
    assert delay_label(seconds) == text


def test_delay_label_covers_every_allowed_delay():
    for seconds in ALLOWED_DELAYS:
        assert delay_label(seconds)


@pytest.mark.parametrize("seconds", [0, 2, 7, -1, "5", None, 5.5])
def test_delay_label_rejects_other_delays(seconds):
    with pytest.raises(ValueError):
        delay_label(seconds)


@pytest.mark.parametrize(
    "total, text",
    [
        (1, "You won! You clicked all 1 number in order."),
        (10, "You won! You clicked all 10 numbers in order."),
    ],
)
def test_win_message(total, text):
    assert win_message(total) == text


@pytest.mark.parametrize("total", [0, -1])
def test_win_message_rejects_non_positive_totals(total):
    with pytest.raises(ValueError):
        win_message(total)


def test_win_and_lose_messages_differ():
    assert win_message(10) != lose_message(10)
