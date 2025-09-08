# streamlit_app.py
from __future__ import annotations

import datetime as dt
from typing import Dict, List

import numpy as np
import pandas as pd
import streamlit as st

import config
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame as DataTimeFrame
from alpaca.data.historical.client import MarketDataClient
from alpaca.trading.client import TradingClient


# ---------- UI Basics ----------
st.set_page_config(page_title="RSI Mean-Reversion – Aktien-Swing", layout="wide")

st.title("RSI Mean-Reversion Bot – Aktien-Swing")

with st.sidebar:
    st.header("Steuerung")
    tf_choice = st.radio(
        "Timeframe",
        options=["1Day"],  # IEX (Paper) liefert zuverlässig nur Daily
        index=0,
        help="IEX im Paper-Account liefert Daily-Bars. Intraday ist hier absichtlich deaktiviert.",
    )
    if config.APP.data_feed.name.lower() == "iex" and tf_choice != "1Day":
        st.info("IEX liefert im Paper-Account keine Intraday-Bars – umgestellt auf 1Day.")
        tf_choice = "1Day"

# ---------- Clients ----------
trading: TradingClient = config.get_trading_client()
mkt: MarketDataClient = config.get_market_client()


# ---------- Helper ----------
def utc_now() -> dt.datetime:
    # timezone-aware UTC (keine Deprecation-Warnung)
    return dt.datetime.now(dt.timezone.utc)


@st.cache_data(show_spinner=False, ttl=300)
def fetch_bars(
    symbols: List[str], timeframe: str, days_back: int = 300
) -> Dict[str, pd.DataFrame]:
    """
    Holt Bars via MarketDataClient (eigener Endpoint!), IEX/SIP je nach Config.
    Gibt pro Symbol ein DataFrame mit Spalten ['open','high','low','close','volume'] zurück.
    """
    tf: DataTimeFrame = config.TF_MAP.get(timeframe, DataTimeFrame.Day)

    end = utc_now()
    start = end - dt.timedelta(days=days_back)

    out: Dict[str, pd.DataFrame] = {}

    # Alpaca erlaubt Multi-Symbol-Requests, wir gehen bewusst symbolweise (robuster)
    for sym in symbols:
        req = StockBarsRequest(
            symbol_or_symbols=[sym],
            timeframe=tf,
            start=start,
            end=end,
            limit=1000,
            feed=config.APP.data_feed,
        )
        try:
            resp = mkt.get_stock_bars(req)
            bars = resp.df  # MultiIndex: (symbol, timestamp)
            if bars is None or bars.empty:
                out[sym] = pd.DataFrame()
                continue

            # nur das eine Symbol, Index glätten
            df = bars.xs(sym, level=0)
            df = df.reset_index().rename(columns={"timestamp": "time"})
            df = df.set_index("time").sort_index()

            # nur die relevanten Spalten
            keep = ["open", "high", "low", "close", "volume"]
            df = df[keep]

            out[sym] = df
        except Exception as e:
            out[sym] = pd.DataFrame()
    return out


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


# ---------- Account-Kacheln ----------
def fmt_usd(x: float | str) -> str:
    try:
        return f"{float(x):,.2f} USD"
    except Exception:
        return str(x)


try:
    account = trading.get_account()
    col1, col2, col3 = st.columns(3)
    col1.metric("Equity", fmt_usd(account.equity))
    col2.metric("Cash", fmt_usd(account.cash))
    col3.metric("Buying Power", fmt_usd(account.buying_power))
except Exception as e:
    st.warning(f"Konto konnte nicht geladen werden: {e}")

# ---------- Offene Positionen ----------
st.subheader("Offene Positionen")
try:
    positions = trading.get_all_positions()
    if not positions:
        st.info("Keine offenen Positionen (oder Trading-Endpoint nicht verfügbar).")
    else:
        rows = []
        for p in positions:
            rows.append(
                {
                    "Symbol": p.symbol,
                    "Qty": float(p.qty),
                    "Entry": float(p.avg_entry_price),
                    "Unrealized PnL": float(p.unrealized_pl),
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
except Exception as e:
    st.warning(f"Positionen konnten nicht geladen werden: {e}")

# ---------- Watchlist-Signale ----------
st.subheader("Watchlist-Signale")

bars_map = fetch_bars(config.APP.symbols, tf_choice, days_back=500)

grid = st.columns(4)
for i, sym in enumerate(config.APP.symbols):
    with grid[i % 4]:
        st.markdown(f"**{sym}:**")
        df = bars_map.get(sym, pd.DataFrame())
        if df is None or df.empty:
            st.write("Keine Daten vom Feed")
            continue

        df = df.copy()
        df["rsi"] = rsi(df["close"], period=config.APP.rsi_period)

        latest = df.iloc[-1]
        last_rsi = float(latest["rsi"])

        signal = "—"
        if last_rsi <= config.APP.rsi_lower:
            signal = "📉 Oversold → Watch LONG"
        elif last_rsi >= config.APP.rsi_upper:
            signal = "📈 Overbought → Watch EXIT"

        st.write(f"RSI: {last_rsi:.1f} • TF: {tf_choice}")
        st.write(signal)

# Fußzeile
st.caption(
    f"Watchlist: {', '.join(config.APP.symbols)} • Timeframe: {tf_choice} • "
    f"Feed: {config.APP.data_feed.name.lower()} • Letzte Aktualisierung: {utc_now():%Y-%m-%d %H:%M:%S %Z}"
)
