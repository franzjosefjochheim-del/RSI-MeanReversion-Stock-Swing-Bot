# minimal
import pandas as pd
import config

def rsi(series: pd.Series, length: int = None) -> pd.Series:
    length = length or config.RSI_LEN
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    roll_up = up.ewm(alpha=1/length, adjust=False).mean()
    roll_down = down.ewm(alpha=1/length, adjust=False).mean()
    rs = roll_up / roll_down
    return 100 - (100 / (1 + rs))

def generate_signal_from_df(df: pd.DataFrame) -> str:
    if "close" not in df.columns or df.empty:
        return "HOLD"
    r = rsi(df["close"]).iloc[-1]
    if r <= config.RSI_OVERSOLD:
        return "BUY"
    if r >= config.RSI_OVERBOUGHT:
        return "SELL"
    return "HOLD"
