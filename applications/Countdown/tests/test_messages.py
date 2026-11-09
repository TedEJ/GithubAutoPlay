import pytest

from countdown.game import ALLOWED_DELAYS
from countdown.messages import delay_label, lose_message


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
