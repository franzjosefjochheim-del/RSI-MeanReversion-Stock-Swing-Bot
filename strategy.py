import pandas as pd
import numpy as np
import config

def rsi(series: pd.Series, n=config.RSI_LEN) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = up / (down + 1e-9)
    return 100 - (100 / (1 + rs))

def generate_signal_from_df(df: pd.DataFrame):
    """Erwartet DataFrame mit Spalten 'close'; gibt 'BUY'/'SELL'/'HOLD' zurück."""
    closes = df["close"].astype(float)
    r = rsi(closes).iloc[-1]
    if r <= config.BUY_RSI_MAX:  # stark überverkauft -> Mean Reversion Long
        return "BUY"
    if r >= config.EXIT_RSI_MIN: # Erholung -> Exit
        return "SELL"
    return "HOLD"
