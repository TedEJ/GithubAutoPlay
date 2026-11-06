# Countdown

Countdown is a small memory game written in Python with a GUI window. It is the first project in this repository, and it is built step by step by Claude from GitHub issues. The overview and the plan are in issue #13.

## The idea
The numbers 1 to 10 appear at different places in the window. After a short delay every number turns into an **X**, so the player no longer knows which number is where. The player must then find the numbers and click them with the mouse in order: 1, 2, 3 and so on up to 10.

## Rules
1. **Start:** the player chooses how long the numbers stay visible: **1, 5 or 10 seconds**. A shorter time is harder.
2. **Show:** the numbers 1 to 10 appear at ten different places in the window. They must not overlap and must stay fully inside the window.
3. **Hide:** when the chosen time has passed, every number turns into an **X**. The positions stay the same.
4. **Play:** the player clicks the X marks with the mouse, trying to click number 1 first, then 2, then 3, and so on.
5. **Correct click:** if the clicked X is the next number in order, it is marked as found and the game continues.
6. **Wrong click:** if the clicked X is any other number, the game is lost immediately.
7. **Lose screen:** after a loss, **all ten numbers are shown again** at their places, together with **how many correct numbers were clicked** before the mistake.
8. **Win:** if the player clicks all ten numbers in order, the game is won.
9. **Play again:** after a win or a loss the player can start a new game.

## Technology
- **Language:** Python
- **GUI:** `tkinter`, which is part of Python and needs no installation
- **Tests:** `pytest`. The game logic is kept separate from the GUI, so the tests can run in the check `checks` on GitHub, which has no screen.

## Planned steps
The work is split into small issues, one step at a time. The full list with workload levels is in issue #13. In short:
1. Folder and README (done)
2. Project skeleton, `pytest` and a test step in the `checks` job (done)
3. Game logic without a GUI, with unit tests
4. GUI window that draws the numbers
5. Hide timer (1, 5 or 10 seconds)
6. Clicking in order, and the lose screen
7. Start screen where the player picks the delay
8. Win screen and play again
9. Polish

## How to run
The game is not playable yet, but the project skeleton runs. You need Python 3.10 or newer.

Run the commands from the `applications/Countdown` folder:

```
python -m countdown
```

This prints a short message and exits. The window and the game arrive in later steps.

## How to run the tests
Install the test tool once, and then run the tests:

```
python -m pip install -r requirements.txt
python -m pytest
```

The same tests run automatically in the check `checks` on every pull request. The game logic must not import `tkinter`, because the check runs without a display. Only the GUI module may use it.
