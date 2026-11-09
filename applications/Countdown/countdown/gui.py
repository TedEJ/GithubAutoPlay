"""The Countdown window. The only module that imports ``tkinter``.

Thin on purpose: it draws what the ``Game`` holds, passes mouse clicks to it
and contains no rules.
"""

import tkinter as tk

from countdown.game import Phase
from countdown.layout import number_at
from countdown.messages import lose_message
from countdown.settings import (
    BOX_SIZE,
    MESSAGE_BAR_HEIGHT,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    new_game,
)

BACKGROUND = "#1e1e2e"
BAR_BACKGROUND = "#181825"
BOX_FILL = "#313244"
BOX_OUTLINE = "#89b4fa"
TEXT_COLOR = "#cdd6f4"
FOUND_FILL = "#a6e3a1"
FOUND_OUTLINE = "#40a02b"
FOUND_TEXT = "#1e1e2e"
MESSAGE_COLOR = "#f38ba8"


def draw_game(canvas, game):
    """Draw every box of ``game``, and the lose message after a loss."""
    canvas.delete("all")
    canvas.create_rectangle(
        0, WINDOW_HEIGHT, WINDOW_WIDTH, WINDOW_HEIGHT + MESSAGE_BAR_HEIGHT,
        fill=BAR_BACKGROUND, outline="",
    )
    for number, (x, y) in game.positions.items():
        found = number in game.found
        canvas.create_rectangle(
            x, y, x + BOX_SIZE, y + BOX_SIZE,
            fill=FOUND_FILL if found else BOX_FILL,
            outline=FOUND_OUTLINE if found else BOX_OUTLINE,
            width=2,
        )
        canvas.create_text(
            x + BOX_SIZE // 2,
            y + BOX_SIZE // 2,
            text=str(number) if (found or game.numbers_visible) else "X",
            fill=FOUND_TEXT if found else TEXT_COLOR,
            font=("Helvetica", BOX_SIZE // 2, "bold"),
        )
    if game.phase is Phase.LOST:
        canvas.create_text(
            WINDOW_WIDTH // 2,
            WINDOW_HEIGHT + MESSAGE_BAR_HEIGHT // 2,
            text=lose_message(game.correct_count),
            fill=MESSAGE_COLOR,
            font=("Helvetica", 18, "bold"),
        )


def create_app(root):
    """Build the canvas on ``root``, start a round and return ``(canvas, game)``."""
    canvas = tk.Canvas(
        root,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT + MESSAGE_BAR_HEIGHT,
        bg=BACKGROUND,
        highlightthickness=0,
    )
    canvas.pack()
    game = new_game()
    draw_game(canvas, game)

    def hide_numbers():
        if game.phase is Phase.SHOWING:
            game.hide()
            draw_game(canvas, game)

    def on_click(event):
        if game.phase is not Phase.PLAYING:
            return
        number = number_at(game.positions, BOX_SIZE, event.x, event.y)
        if number is None:
            return
        game.click(number)
        draw_game(canvas, game)

    canvas.bind("<Button-1>", on_click)
    root.after(game.delay_milliseconds, hide_numbers)
    return canvas, game


def run():
    """Open the window and run until it is closed. Returns the exit code."""
    try:
        root = tk.Tk()
    except tk.TclError as error:
        print(f"Countdown could not open a window: {error}")
        return 1
    root.title("Countdown")
    root.resizable(False, False)
    create_app(root)
    root.mainloop()
    return 0
