"""Tiny RSI + SMA strategy used as a test fixture. Contains a deliberate lookahead bug."""
import pandas as pd

FAST, SLOW, RSI_PERIOD = 10, 50, 14


def rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    return 100 - 100 / (1 + gain / loss)


def signals(df: pd.DataFrame) -> pd.Series:
    fast = df["close"].rolling(FAST).mean()
    slow = df["close"].rolling(SLOW).mean()
    # BUG: shift(-1) peeks at the next bar's close, which is lookahead bias.
    next_close = df["close"].shift(-1)
    return ((fast > slow) & (rsi(df["close"]) < 70) & (next_close > df["close"])).astype(int)
