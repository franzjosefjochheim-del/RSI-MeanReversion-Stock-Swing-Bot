# streamlit_app.py
from __future__ import annotations

import datetime as dt
from typing import Dict, List

import numpy as np
import pandas as pd
import streamlit as st

import config  # liefert get_market_data_client(), data_feed_label(), SYMBOLS usw.

# Zusätzliche Alpaca-Imports (nur Typen/Requests, kein alter MarketDataClient-Import!)
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame as DataTimeFrame
from alpaca.trading.client import TradingClient  # Teil von alpaca-py (OK)


# ---------------- UI-Basis ----------------
st.set_page_config(page_title="RSI Mean-Reversion – Aktien-Swing", layout="wide")
st.title("RSI Mean-Reversion Bot – Aktien-Swing")

with st.sidebar:
    st.header("Steuerung")
    # IEX (Paper) liefert zuverlässig Daily-Bars
    tf_choice = st.radio(
        "Timeframe",
        options=["1Day"],
        index=0,
        help="IEX im Paper-Account liefert Daily-Bars. Intraday ist deaktiviert.",
    )
    st.caption(f"Feed: **{config.data_feed_label()}**")


# ---------------- Clients ----------------
# Market Data Client aus config (intern: StockHistoricalDataClient)
md_client = config.get_market_data_client()

# TradingClient (nur zum Anzeigen von Account/Positionen; Orders platzieren wir hier nicht)
trading = TradingClient(config.API_KEY, config.API_SECRET, paper=True)


# ---------------- Helfer ----------------
def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


@st.cache_data(show_spinner=False, ttl=300)
def fetch_bars(symbols: List[str], timeframe: str, days_back: int = 500) -> Dict[str, pd.DataFrame]:
    """
    Holt Bars via alpaca-py Market Data Client (IEX/SIP je nach Config).
    Gibt pro Symbol ein DataFrame mit Spalten ['open','high','low','close','volume'] zurück.
    """
    tf: DataTimeFrame = DataTimeFrame.Day  # einzig aktivierter TF in der UI
    end = utc_now()
    start = end - dt.timedelta(days=days_back)

    out: Dict[str, pd.DataFrame] = {}
    for sym in symbols:
        try:
            req = StockBarsRequest(
                symbol_or_symbols=[sym],
                timeframe=tf,
                start=start,
                end=end,
                limit=1000,
                feed=config.API_DATA_FEED,  # "iex" oder "sip"
            )
            resp = md_client.get_stock_bars(req)
            bars = resp.df  # MultiIndex (symbol, timestamp) → DataFrame

            if bars is None or bars.empty:
                out[sym] = pd.DataFrame()
                continue

            df = bars.xs(sym, level=0).reset_index().rename(columns={"timestamp": "time"})
            df = df.set_index("time").sort_index()
            out[sym] = df[["open", "high", "low", "close", "volume"]]
        except Exception:
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


def fmt_usd(x: float | str) -> str:
    try:
        return f"{float(x):,.2f} USD"
    except Exception:
        return str(x)


# ---------------- Account-Kacheln ----------------
try:
    account = trading.get_account()
    c1, c2, c3 = st.columns(3)
    c1.metric("Equity", fmt_usd(account.equity))
    c2.metric("Cash", fmt_usd(account.cash))
    c3.metric("Buying Power", fmt_usd(account.buying_power))
except Exception as e:
    st.warning(f"Konto konnte nicht geladen werden: {e}")


# ---------------- Offene Positionen ----------------
st.subheader("Offene Positionen")
try:
    positions = trading.get_all_positions()
    if not positions:
        st.info("Keine offenen Positionen (oder Trading-Endpoint nicht verfügbar).")
    else:
        rows = []
        for p in positions:
            rows.append({
                "Symbol": p.symbol,
                "Qty": float(p.qty),
                "Entry": float(p.avg_entry_price),
                "Unrealized PnL": float(p.unrealized_pl),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
except Exception as e:
    st.warning(f"Positionen konnten nicht geladen werden: {e}")


# ---------------- Watchlist-Signale ----------------
st.subheader("Watchlist-Signale")
bars_map = fetch_bars(config.SYMBOLS, tf_choice, days_back=500)

cols = st.columns(4)
for i, sym in enumerate(config.SYMBOLS):
    with cols[i % 4]:
        st.markdown(f"**{sym}:**")
        df = bars_map.get(sym, pd.DataFrame())
        if df is None or df.empty:
            st.write(f"⚠️ Keine Bars für {sym} (Feed: {config.data_feed_label()}, TF: {tf_choice})")
            continue

        df = df.copy()
        df["rsi"] = rsi(df["close"], period=config.RSI_PERIOD)
        last_rsi = float(df["rsi"].iloc[-1])

        if last_rsi <= config.RSI_LOWER:
            signal = "📉 Oversold → Watch LONG"
        elif last_rsi >= config.RSI_UPPER:
            signal = "📈 Overbought → Watch EXIT"
        else:
            signal = "—"

        st.write(f"RSI: {last_rsi:.1f} • TF: {tf_choice}")
        st.write(signal)

st.caption(
    f"Watchlist: {', '.join(config.SYMBOLS)} • TF: {tf_choice} • "
    f"Feed: {config.data_feed_label()} • Letzte Aktualisierung: {utc_now():%Y-%m-%d %H:%M:%S %Z}"
)
