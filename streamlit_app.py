# streamlit_app.py
import math
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
import yfinance as yf

import config  # nutzt: get_api(), SYMBOLS, TIMEFRAME, FALLBACK_TIMEFRAME, RSI_* , API_DATA_FEED


# =======================================
# Hilfsfunktionen: Daten & Indikatoren
# =======================================

@st.cache_data(show_spinner=False, ttl=300)
def fetch_bars_alpaca(symbol: str, timeframe: str, limit: int = 300) -> pd.DataFrame:
    """
    Versucht Bars von Alpaca zu holen (nur sinnvoll mit SIP).
    Gibt DataFrame mit Spalten ['close'] und DatetimeIndex zurück.
    """
    api = config.get_api()
    # Map Streamlit-Timeframe -> Alpaca
    tf_map = {"1Day": "1Day", "1Hour": "1Hour"}
    tf = tf_map.get(timeframe, "1Day")

    # Ende/Start-Zeitraum
    end = pd.Timestamp.utcnow(tz="UTC")
    if tf == "1Hour":
        start = end - pd.Timedelta(days=30)
    else:
        start = end - pd.Timedelta(days=365)

    try:
        bars = api.get_bars(
            symbol,
            tf,
            start=start.isoformat(),
            end=end.isoformat(),
            limit=limit,
            adjustment="raw",
        )
        if bars is None or len(bars) == 0:
            return pd.DataFrame()
        df = bars.df
        # Bei mehreren Symbolen liefert Alpaca MultiIndex (symbol, time)
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level=0)
        df = df.sort_index()
        return df[["close"]].copy()
    except Exception:
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=300)
def fetch_bars_yf(symbol: str, timeframe: str, limit: int = 300) -> pd.DataFrame:
    """
    Holt Bars von Yahoo Finance.
    Unterstützt '1Day' (1d) und '1Hour' (60m, begrenztes Fenster).
    Gibt DataFrame mit Spalten ['close'] und DatetimeIndex (UTC) zurück.
    """
    if timeframe == "1Hour":
        interval = "60m"
        period = "60d"  # yfinance-Beschränkung
    else:
        interval = "1d"
        period = "2y"

    try:
        hist = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
        if hist is None or hist.empty:
            return pd.DataFrame()
        hist = hist.rename(columns=str.lower)
        # yfinance ist in lokaler TZ; auf UTC vereinheitlichen
        hist.index = pd.to_datetime(hist.index, utc=True)
        df = hist[["close"]].copy()
        if limit and len(df) > limit:
            df = df.iloc[-limit:]
        return df
    except Exception:
        return pd.DataFrame()


def fetch_bars(symbol: str, timeframe: str, limit: int = 300) -> pd.DataFrame:
    """
    Vereinheitlichte Abfrage:
    - Wenn SIP: zuerst Alpaca, dann Fallback yfinance (zur Sicherheit).
    - Wenn IEX: direkt yfinance (IEX liefert keine historischen OHLC-Bars).
    """
    if config.API_DATA_FEED == "sip":
        df = fetch_bars_alpaca(symbol, timeframe, limit)
        if df.empty:
            df = fetch_bars_yf(symbol, timeframe, limit)
        return df
    else:  # iex
        return fetch_bars_yf(symbol, timeframe, limit)


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Klassischer RSI (Wilder) auf Schlusskursen."""
    if series is None or series.empty:
        return pd.Series(dtype=float)

    delta = series.diff()
    gain = (delta.where(delta > 0, 0.0)).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1 / period, adjust=False).mean()

    rs = gain / loss.replace(0, pd.NA)
    rsi_vals = 100 - (100 / (1 + rs))
    return rsi_vals.fillna(50.0)


def generate_signal(close: pd.Series, period: int, lower: float, upper: float) -> tuple[str, float]:
    """
    Mean-Reversion RSI:
      - BUY  wenn RSI < lower
      - SELL wenn RSI > upper
      - sonst HOLD
    Gibt (Signal, letzter_RSI) zurück.
    """
    if close is None or len(close) < max(20, period + 2):
        return "NO DATA", float("nan")

    r = rsi(close, period)
    last = float(r.iloc[-1])
    if last < lower:
        return "BUY", last
    if last > upper:
        return "SELL", last
    return "HOLD", last


# =======================================
# UI / Streamlit
# =======================================

st.set_page_config(page_title="RSI Mean-Reversion – Aktien-Swing", layout="wide")
st.title("RSI Mean-Reversion Bot – Aktien-Swing")

# Sidebar-Steuerung
with st.sidebar:
    st.markdown("### Steuerung")

    # Timeframe-Auswahl
    tf_choice = st.radio("Timeframe", options=["1Day", "1Hour"], index=0, horizontal=False)

    # IEX kann keine Intraday-Bars → zurück auf Daily
    if config.API_DATA_FEED == "iex" and tf_choice == "1Hour":
        st.info("IEX-Feed liefert **keine Intraday-Bars**. Timeframe wurde auf **1Day** gesetzt.")
        tf_choice = "1Day"

    if st.button("Aktualisieren"):
        st.cache_data.clear()
        st.rerun()

# Account-Kacheln
api = config.get_api()
try:
    account = api.get_account()
    col1, col2, col3 = st.columns(3)
    col1.metric("Equity", f"{float(account.equity):,.2f} USD")
    col2.metric("Cash", f"{float(account.cash):,.2f} USD")
    col3.metric("Buying Power", f"{float(account.buying_power):,.2f} USD")
except Exception as e:
    st.warning(f"⚠️ Konto konnte nicht geladen werden: {e}")

# Offene Positionen
st.subheader("Offene Positionen")
try:
    positions = api.get_positions()  # <- korrekt (kein get_all_positions in deiner Version)
    if not positions:
        st.write("empty")
    else:
        rows = []
        for p in positions:
            rows.append(
                {
                    "Symbol": p.symbol,
                    "Qty": float(p.qty),
                    "Entry": float(p.avg_entry_price),
                    "Unrealized PnL": float(p.unrealized_pl) if p.unrealized_pl is not None else 0.0,
                }
            )
        st.dataframe(pd.DataFrame(rows), height=240)
except Exception as e:
    st.warning(f"⚠️ Positionen konnten nicht geladen werden: {e}")

# Watchlist-Signale
st.subheader("Watchlist-Signale")

grid = st.columns(len(config.SYMBOLS))
now_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

for i, sym in enumerate(config.SYMBOLS):
    with grid[i]:
        st.markdown(f"**{sym}:**")
        df = fetch_bars(sym, tf_choice, limit=500)

        if df.empty or "close" not in df.columns or df["close"].dropna().empty:
            st.write("Keine Daten vom Feed")
            continue

        sig, rsi_val = generate_signal(
            df["close"], config.RSI_PERIOD, config.RSI_LOWER, config.RSI_UPPER
        )

        if math.isnan(rsi_val):
            st.write("Zu wenige Datenpunkte")
        else:
            st.write(f"RSI: **{rsi_val:.1f}**  •  Signal: **{sig}**")

        # Mini-Chart (Close)
        try:
            st.line_chart(df["close"].tail(120))
        except Exception:
            pass

# Fußzeile / Meta
st.caption(
    f"Watchlist: {', '.join(config.SYMBOLS)} • Timeframe: {tf_choice} "
    f"• Feed: {'Alpaca/SIP' if config.API_DATA_FEED == 'sip' else 'Yahoo (Fallback für IEX)'} "
    f"• Letzte Aktualisierung: {now_utc}"
)
