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
3. Game logic without a GUI, with unit tests (done): number placement and game state
4. GUI window that draws the numbers (done)
5. Hide timer (done; the delay is chosen on the start screen in step 7)
6. Clicking in order, and the lose screen (done), and a restart button (done)
7. Start screen where the player picks the delay (done), with a Change delay button
8. Win screen and play again
9. Polish

## How to run
The game is playable up to the lose screen. The window opens on a **start screen** with three buttons, **1 second**, **5 seconds** and **10 seconds**: the button you click decides how long the numbers stay visible. Then the numbers 1 to 10 appear at ten different places and every number turns into an **X** after the chosen time. You click the X marks in order, 1, 2, 3 and so on: a correct click turns the box green and shows its number, and a wrong click loses at once. After a loss all ten numbers are shown again, and the strip below the play area says how many numbers you clicked correctly. The **Restart** button below the play area starts a new round at any time, with new places for the numbers and the same delay. The **Change delay** button goes back to the start screen at any time. The win screen comes in a later step. You need Python 3.10 or newer with `tkinter`. It is included in the standard Python installers for Windows and macOS; on some Linux systems it is a separate package (for example `python3-tk` on Debian and Ubuntu).

Run the command from the `applications/Countdown` folder:

```
python -m countdown
```

If `tkinter` is missing, or there is no screen, the program prints a short explanation and exits with an error code instead of crashing.

## How to run the tests
Install the test tool once, and then run the tests:

```
python -m pip install -r requirements.txt
python -m pytest
```

The same tests run automatically in the check `checks` on every pull request. The game logic must not import `tkinter`, because the check runs without a display. Only the GUI module may use it.
