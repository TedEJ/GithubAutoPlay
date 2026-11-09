"""The Countdown window. The only module that imports ``tkinter``.

Thin on purpose: it draws what the ``Game`` holds, passes mouse clicks to it
and contains no rules.
"""

import tkinter as tk

from countdown.game import ALLOWED_DELAYS, Phase
from countdown.layout import number_at
from countdown.messages import delay_label, lose_message, win_message
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
WIN_MESSAGE_COLOR = "#a6e3a1"


def draw_game(canvas, game):
    """Draw every box of ``game``, and the lose or win message after a round."""
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
    message = None
    if game.phase is Phase.LOST:
        message, color = lose_message(game.correct_count), MESSAGE_COLOR
    elif game.phase is Phase.WON:
        message, color = win_message(len(game.positions)), WIN_MESSAGE_COLOR
    if message is not None:
        canvas.create_text(
            WINDOW_WIDTH // 2,
            WINDOW_HEIGHT + MESSAGE_BAR_HEIGHT // 2,
            text=message,
            fill=color,
            font=("Helvetica", 18, "bold"),
        )


def create_app(root):
    """Build the window content on ``root`` and show the start screen.

    Returns ``(canvas, state, controls)``. ``state["game"]`` is the round that
    is running now, or ``None`` while the start screen is shown. ``controls``
    holds the widgets: ``start_frame``, ``play_frame``, ``delay_buttons``
    (delay in seconds -> button), ``restart`` and ``change_delay``.
    """
    total_height = WINDOW_HEIGHT + MESSAGE_BAR_HEIGHT
    state = {"game": None, "timer": None}

    start_frame = tk.Frame(root, width=WINDOW_WIDTH, height=total_height, bg=BACKGROUND)
    start_frame.pack_propagate(False)
    tk.Label(
        start_frame,
        text="How long should the numbers be visible?",
        bg=BACKGROUND,
        fg=TEXT_COLOR,
        font=("Helvetica", 20, "bold"),
    ).pack(pady=(total_height // 3, 20))
    delay_buttons = {}

    play_frame = tk.Frame(root, bg=BACKGROUND)
    canvas = tk.Canvas(
        play_frame,
        width=WINDOW_WIDTH,
        height=total_height,
        bg=BACKGROUND,
        highlightthickness=0,
    )
    canvas.pack()

    def cancel_timer():
        # A hide timer from an earlier round must never hide the numbers of
        # the new one, so the old timer is cancelled first. (cancelling a timer
        # that has already run does no harm.)
        if state["timer"] is not None:
            root.after_cancel(state["timer"])
            state["timer"] = None

    def show_start_screen():
        cancel_timer()
        state["game"] = None
        play_frame.pack_forget()
        start_frame.pack()

    def start_round(delay_seconds):
        cancel_timer()
        start_frame.pack_forget()
        play_frame.pack()
        game = new_game(delay_seconds=delay_seconds)
        state["game"] = game
        draw_game(canvas, game)
        state["timer"] = root.after(game.delay_milliseconds, lambda: hide_numbers(game))

    def hide_numbers(game):
        # Second guard: only act on the round this timer was made for.
        if game is state["game"] and game.phase is Phase.SHOWING:
            game.hide()
            draw_game(canvas, game)

    def on_click(event):
        game = state["game"]
        if game is None or game.phase is not Phase.PLAYING:
            return
        number = number_at(game.positions, BOX_SIZE, event.x, event.y)
        if number is None:
            return
        game.click(number)
        draw_game(canvas, game)

    def restart():
        # Same delay as the round that is running now.
        if state["game"] is not None:
            start_round(state["game"].delay_seconds)

    for seconds in ALLOWED_DELAYS:
        button = tk.Button(
            start_frame,
            text=delay_label(seconds),
            width=14,
            command=lambda seconds=seconds: start_round(seconds),
        )
        button.pack(pady=6)
        delay_buttons[seconds] = button

    canvas.bind("<Button-1>", on_click)
    button_row = tk.Frame(play_frame, bg=BACKGROUND)
    button_row.pack(pady=6)
    restart_button = tk.Button(button_row, text="Restart", command=restart)
    restart_button.pack(side="left", padx=6)
    change_delay_button = tk.Button(
        button_row, text="Change delay", command=show_start_screen
    )
    change_delay_button.pack(side="left", padx=6)
    show_start_screen()
    controls = {
        "start_frame": start_frame,
        "play_frame": play_frame,
        "delay_buttons": delay_buttons,
        "restart": restart_button,
        "change_delay": change_delay_button,
    }
    return canvas, state, controls


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
