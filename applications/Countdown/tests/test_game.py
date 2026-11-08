import pytest

from countdown.game import ALLOWED_DELAYS, Game, Phase
from countdown.layout import place_numbers

POSITIONS = {n: (n * 70, 10) for n in range(1, 11)}


def new_game(delay=5):
    return Game(POSITIONS, delay)


def playing_game():
    game = new_game()
    game.hide()
    return game


# --- rule 1/2: start, delay and positions

@pytest.mark.parametrize("delay", [1, 5, 10])
def test_allowed_delays(delay):
    assert new_game(delay).delay_seconds == delay


@pytest.mark.parametrize("delay", [0, 2, 3, 15, -1, None, "5", 5.5])
def test_invalid_delay_raises_value_error(delay):
    with pytest.raises(ValueError):
        new_game(delay)


def test_allowed_delays_constant():
    assert ALLOWED_DELAYS == (1, 5, 10)


def test_positions_must_be_the_numbers_1_to_10():
    with pytest.raises(ValueError):
        Game({n: (0, 0) for n in range(1, 10)}, 5)
    with pytest.raises(ValueError):
        Game({n: (0, 0) for n in range(2, 12)}, 5)


def test_works_with_place_numbers():
    game = Game(place_numbers(800, 600, 60), 5)
    assert game.phase is Phase.SHOWING


def test_new_game_starts_in_showing():
    game = new_game()
    assert game.phase is Phase.SHOWING
    assert game.next_number == 1
    assert game.found == ()
    assert game.correct_count == 0


# --- rule 3: hide

def test_hide_moves_to_playing_and_keeps_positions():
    game = new_game()
    before = dict(game.positions)
    game.hide()
    assert game.phase is Phase.PLAYING
    assert dict(game.positions) == before == POSITIONS


def test_positions_are_read_only_and_copied():
    source = dict(POSITIONS)
    game = Game(source, 5)
    source[1] = (999, 999)
    assert game.positions[1] == POSITIONS[1]
    with pytest.raises(TypeError):
        game.positions[1] = (0, 0)


def test_hide_twice_raises():
    game = playing_game()
    with pytest.raises(ValueError):
        game.hide()


@pytest.mark.parametrize("finish", ["lost", "won"])
def test_hide_after_the_game_ended_raises(finish):
    game = playing_game()
    if finish == "lost":
        game.click(2)
    else:
        for n in range(1, 11):
            game.click(n)
    with pytest.raises(ValueError):
        game.hide()


# --- rules 4/5: correct clicks

def test_correct_clicks_in_order():
    game = playing_game()
    for n in range(1, 10):
        game.click(n)
        assert game.phase is Phase.PLAYING
        assert game.found == tuple(range(1, n + 1))
        assert game.correct_count == n
        assert game.next_number == n + 1


# --- rule 6/7: wrong click loses at once

@pytest.mark.parametrize("correct_before, wrong", [(0, 2), (0, 10), (4, 9), (4, 2), (9, 1)])
def test_wrong_click_loses_immediately(correct_before, wrong):
    game = playing_game()
    for n in range(1, correct_before + 1):
        game.click(n)
    game.click(wrong)
    assert game.phase is Phase.LOST
    assert game.correct_count == correct_before
    assert game.found == tuple(range(1, correct_before + 1))


def test_clicking_an_already_found_number_loses():
    game = playing_game()
    game.click(1)
    game.click(1)
    assert game.phase is Phase.LOST
    assert game.correct_count == 1


def test_positions_still_available_after_a_loss():
    game = playing_game()
    game.click(5)
    assert game.phase is Phase.LOST
    assert dict(game.positions) == POSITIONS


def test_unknown_number_raises_and_does_not_change_state():
    game = playing_game()
    for bad in (0, 11, -1, None, "1"):
        with pytest.raises(ValueError):
            game.click(bad)
    assert game.phase is Phase.PLAYING
    assert game.correct_count == 0


# --- rule 8: win

def test_win_after_ten_correct_clicks():
    game = playing_game()
    for n in range(1, 11):
        game.click(n)
    assert game.phase is Phase.WON
    assert game.correct_count == 10
    assert game.found == tuple(range(1, 11))
    assert game.next_number is None


# --- clicks in the wrong phase

def test_click_while_showing_raises():
    game = new_game()
    with pytest.raises(ValueError):
        game.click(1)
    assert game.phase is Phase.SHOWING


def test_click_after_loss_raises():
    game = playing_game()
    game.click(3)
    with pytest.raises(ValueError):
        game.click(1)
    assert game.phase is Phase.LOST


def test_click_after_win_raises():
    game = playing_game()
    for n in range(1, 11):
        game.click(n)
    with pytest.raises(ValueError):
        game.click(1)
    assert game.phase is Phase.WON


# --- a new game is a new object

def test_games_are_independent():
    a, b = new_game(), new_game()
    a.hide()
    a.click(1)
    assert b.phase is Phase.SHOWING and b.correct_count == 0
