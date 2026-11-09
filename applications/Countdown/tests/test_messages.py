import pytest

from countdown.messages import lose_message


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
