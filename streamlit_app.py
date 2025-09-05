# streamlit_app.py
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import streamlit as st
import alpaca_trade_api as tradeapi

import config  # <- nutzt get_api() + Parameter (WATCHLIST, TIMEFRAME, API_DATA_FEED, etc.)


# -------------------------------
# Seite / Sidebar
# -------------------------------
st.set_page_config(page_title="RSI Mean-Reversion – Aktien-Swing", layout="wide")

with st.sidebar:
    st.markdown("### Steuerung")
    st.write("Status: **AKTIV**")
    colA, colB = st.columns(2)
    if colA.button("Aktualisieren"):
        st.rerun()
    # optionaler Pause-Button (UI-only; Bot läuft hier nur als Dashboard)
    st.button("Pause", disabled=True)

st.title("RSI Mean-Reversion Bot – Aktien-Swing")


# -------------------------------
# Hilfsfunktionen (robust)
# -------------------------------
@st.cache_resource(show_spinner=False)
def get_api():
    """Gecachter Alpaca-Client (holt Keys aus config / Render Env)."""
    return config.get_api()


def _normalize_bars_df(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    Normalisiert das Bars-DataFrame:
    - entpackt MultiIndex (symbol, timestamp) -> nur der Symbol-Teil
    - stellt sicher, dass 'close' existiert
    """
    if df is None or len(df) == 0:
        return pd.DataFrame()

    # MultiIndex? -> auf Symbol filtern
    if hasattr(df.index, "levels"):
        try:
            df = df.loc[(symbol,), :].copy()
        except Exception:
            # Falls das Symbol nicht enthalten ist
            return pd.DataFrame()

    # Close-Spalte sicherstellen
    if "close" not in df.columns:
        # fallback: evtl. heißen Spalten je nach API-Version anders
        # häufig: 'c' (Polygon) – hier nicht zu erwarten, aber defensiv:
        if "c" in df.columns:
            df = df.rename(columns={"c": "close"})
        else:
            return pd.DataFrame()

    # leere DF vermeiden
    if df["close"].dropna().empty:
        return pd.DataFrame()

    return df


def fetch_bars(symbol: str, limit: int = 300) -> pd.DataFrame:
    """
    Holt Bars für ein Symbol. Zeigt bei leeren Daten eine freundliche Info.
    """
    api = get_api()
    try:
        bars = api.get_bars(
            symbol,
            config.TIMEFRAME,
            limit=limit,
            feed=config.API_DATA_FEED  # "iex" (kostenlos) oder "sip"
        ).df
        bars = _normalize_bars_df(bars, symbol)
        return bars
    except Exception as e:
        st.write(f"**{symbol}**: Fehler beim Laden der Bars – {e}")
        return pd.DataFrame()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Klassischer RSI (Wilder)."""
    if series is None or series.dropna().empty:
        return pd.Series(dtype=float)
    delta = series.diff()
    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)

    roll_up = pd.Series(up, index=series.index).rolling(period).mean()
    roll_down = pd.Series(down, index=series.index).rolling(period).mean()

    rs = roll_up / (roll_down.replace(0, np.nan))
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val


def format_usd(x) -> str:
    try:
        return f"{float(x):,.2f} USD"
    except Exception:
        return "–"


# -------------------------------
# Metriken (Konto)
# -------------------------------
api = get_api()
try:
    account = api.get_account()
    col1, col2, col3 = st.columns(3)
    col1.metric("Equity", format_usd(account.equity))
    col2.metric("Cash", format_usd(account.cash))
    col3.metric("Buying Power", format_usd(account.buying_power))
except Exception as e:
    st.warning(f"Konto konnte nicht geladen werden: {e}")


# -------------------------------
# Offene Positionen
# -------------------------------
st.subheader("Offene Positionen")
try:
    positions = api.get_positions()
    rows = []
    for p in positions:
        rows.append({
            "Symbol": p.symbol,
            "Qty": float(p.qty),
            "Entry": float(p.avg_entry_price),
            "Unrealized PnL": float(p.unrealized_pl)
        })
    if rows:
        df_pos = pd.DataFrame(rows)
        st.dataframe(df_pos, use_container_width=True)
    else:
        # Leere Tabelle mit Spaltenkopf
        st.dataframe(pd.DataFrame(columns=["Symbol", "Qty", "Entry", "Unrealized PnL"]),
                     use_container_width=True)
except Exception as e:
    st.write(f"Positionen konnten nicht geladen werden: {e}")


# -------------------------------
# Watchlist & RSI-Signale
# -------------------------------
st.subheader("Watchlist-Signale")

# Übersicht: 4 Spalten – für SPY / QQQ / AAPL / MSFT
cols = st.columns(4)

watchlist = getattr(config, "WATCHLIST", ["SPY", "QQQ", "AAPL", "MSFT"])
display_symbols = ["SPY", "QQQ", "AAPL", "MSFT"]
display_symbols = [s for s in display_symbols if s in watchlist]  # nur was existiert

def signal_for_symbol(symbol: str, rsi_lower=30, rsi_upper=70) -> str:
    """
    Ermittelt ein einfaches Mean-Reversion-Signal:
    - RSI < rsi_lower: 'Kauf-Kandidat'
    - RSI > rsi_upper: 'Verkauf-Kandidat'
    - sonst 'Keine Daten / Neutral'
    """
    bars = fetch_bars(symbol, limit=200)
    if bars.empty:
        return f"{symbol}: **Keine Daten vom Feed**"

    closes = bars["close"].astype(float)
    r = rsi(closes, period=14)
    if r.dropna().empty:
        return f"{symbol}: **Keine RSI-Daten**"

    last_rsi = float(r.iloc[-1])
    if last_rsi < rsi_lower:
        return f"{symbol}: RSI {last_rsi:.1f} → **Kauf-Kandidat**"
    if last_rsi > rsi_upper:
        return f"{symbol}: RSI {last_rsi:.1f} → **Verkauf-Kandidat**"
    return f"{symbol}: RSI {last_rsi:.1f} → Neutral"


# Je Symbol in eine eigene Spalte
for idx, sym in enumerate(display_symbols):
    with cols[idx]:
        st.markdown(f"**{sym}:**")
        st.write(signal_for_symbol(sym))


# -------------------------------
# Fußzeile / Meta-Infos
# -------------------------------
st.markdown("---")
now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
st.caption(
    f"Watchlist: {', '.join(watchlist)} • "
    f"Timeframe: **{config.TIMEFRAME}** • Feed: **{config.API_DATA_FEED.upper()}** • "
    f"Letzte Aktualisierung: {now_utc}"
)
