"""The Countdown window. The only module that imports ``tkinter``.

Thin on purpose: it draws what the ``Game`` holds and contains no rules.
"""

import tkinter as tk

from countdown.settings import BOX_SIZE, WINDOW_HEIGHT, WINDOW_WIDTH, new_game

BACKGROUND = "#1e1e2e"
BOX_FILL = "#313244"
BOX_OUTLINE = "#89b4fa"
TEXT_COLOR = "#cdd6f4"


def draw_numbers(canvas, game):
    """Draw every number of ``game`` in a box at its position."""
    canvas.delete("all")
    for number, (x, y) in game.positions.items():
        canvas.create_rectangle(
            x, y, x + BOX_SIZE, y + BOX_SIZE, fill=BOX_FILL, outline=BOX_OUTLINE, width=2
        )
        canvas.create_text(
            x + BOX_SIZE // 2,
            y + BOX_SIZE // 2,
            text=str(number),
            fill=TEXT_COLOR,
            font=("Helvetica", BOX_SIZE // 2, "bold"),
        )


def run():
    """Open the window and run until it is closed. Returns the exit code."""
    try:
        root = tk.Tk()
    except tk.TclError as error:
        print(f"Countdown could not open a window: {error}")
        return 1
    root.title("Countdown")
    root.resizable(False, False)
    canvas = tk.Canvas(
        root, width=WINDOW_WIDTH, height=WINDOW_HEIGHT, bg=BACKGROUND, highlightthickness=0
    )
    canvas.pack()
    draw_numbers(canvas, new_game())
    root.mainloop()
    return 0
