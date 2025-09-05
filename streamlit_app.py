# streamlit_app.py
import math
from typing import List, Tuple, Optional

import numpy as np
import pandas as pd
import streamlit as st

import config


# ==========================
# Streamlit Grund-Konfig
# ==========================
st.set_page_config(
    page_title="RSI Mean-Reversion Bot – Aktien-Swing",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("RSI Mean-Reversion Bot – Aktien-Swing")


# ==========================
# Caching / API
# ==========================
@st.cache_resource(show_spinner=False)
def get_api():
    return config.get_api()


api = get_api()


@st.cache_data(show_spinner=False, ttl=60)
def fetch_bars(
    symbols: List[str], timeframe: str, limit: int, feed: str
) -> pd.DataFrame:
    """
    Holt OHLCV-Bars für Aktien über Alpacas get_bars.
    Gibt ein DataFrame zurück; bei mehreren Symbolen ein MultiIndex (symbol, time),
    bei einem Symbol i. d. R. einfacher Index.
    """
    try:
        # alpaca_trade_api >=3.x
        df = api.get_bars(
            symbols=symbols,
            timeframe=timeframe,
            limit=limit,
            feed=feed,
            adjustment="raw",
        ).df
        return df
    except Exception as e:
        # Für Debug in den Logs
        st.write(f"⚠️ fetch_bars Fehler ({symbols}, {timeframe}): {e}")
        return pd.DataFrame()


def bars_with_fallback(symbol: str, limit: int = 200) -> Tuple[pd.DataFrame, str]:
    """
    Erst den primären TIMEFRAME aus config versuchen, bei zu wenigen Daten
    automatisches Fallback auf FALLBACK_TIMEFRAME.
    Gibt (df, verwendeter_timeframe) zurück – df ist für EIN Symbol gefiltert.
    """
    # Primär
    df_all = fetch_bars([symbol], config.TIMEFRAME, limit, config.API_DATA_FEED)
    df = df_all
    if not df.empty and hasattr(df.index, "levels"):
        # MultiIndex (symbol, time)
        try:
            df = df_all.loc[(symbol,), :].copy()
        except Exception:
            df = pd.DataFrame()

    if df.empty or len(df) < 50:  # für RSI mind. ~50 Datenpunkte sinnvoll
        # Fallback
        df_all_fb = fetch_bars(
            [symbol], config.FALLBACK_TIMEFRAME, limit, config.API_DATA_FEED
        )
        df_fb = df_all_fb
        if not df_fb.empty and hasattr(df_fb.index, "levels"):
            try:
                df_fb = df_all_fb.loc[(symbol,), :].copy()
            except Exception:
                df_fb = pd.DataFrame()
        if not df_fb.empty:
            return df_fb, config.FALLBACK_TIMEFRAME

    return df, config.TIMEFRAME


# ==========================
# RSI-Berechnung & Signal
# ==========================
def compute_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    # Schutz: mind. period+1 Punkte
    if prices is None or len(prices) < period + 1:
        return pd.Series(dtype=float)

    delta = prices.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    # Verhindern von Division durch 0
    rs = avg_gain / (avg_loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.fillna(50.0)  # neutrale Füllung
    return rsi


def rsi_signal_for_symbol(symbol: str) -> Tuple[str, Optional[float], str, str]:
    """
    Liefert (status_text, rsi_wert, timeframe, detail_text)
    status_text: "BUY", "SELL", "HOLD", "Zu wenige Daten", "Keine Daten vom Feed"
    detail_text: Zusatzinformationen/Fehlermeldung
    """
    try:
        df, used_tf = bars_with_fallback(symbol)
        if df.empty or "close" not in df.columns:
            return "Keine Daten vom Feed", None, used_tf, "Kein DataFrame oder 'close' fehlt"

        closes = pd.Series(df["close"]).astype(float)
        rsi_series = compute_rsi(closes, period=config.RSI_PERIOD)
        if rsi_series.empty or math.isnan(rsi_series.iloc[-1]):
            return "Zu wenige Datenpunkte", None, used_tf, "RSI-Berechnung nicht möglich"

        rsi_val = float(rsi_series.iloc[-1])

        if rsi_val <= config.RSI_LOWER:
            sig = "BUY"
        elif rsi_val >= config.RSI_UPPER:
            sig = "SELL"
        else:
            sig = "HOLD"

        return sig, rsi_val, used_tf, ""
    except Exception as e:
        return "Fehler", None, config.TIMEFRAME, str(e)


# ==========================
# Sidebar
# ==========================
with st.sidebar:
    st.subheader("Steuerung")
    st.write("Status: **AKTIV**")
    if st.button("Aktualisieren"):
        st.rerun()
    # Optional: Pause/Start nur, wenn du eine control.py hast
    # (hier ausgelassen für Dashboard-only).


# ==========================
# Header-Kennzahlen
# ==========================
col1, col2, col3 = st.columns(3)
try:
    account = api.get_account()
    with col1:
        st.metric("Equity", f"{float(account.equity):,.2f} USD")
    with col2:
        st.metric("Cash", f"{float(account.cash):,.2f} USD")
    with col3:
        st.metric("Buying Power", f"{float(account.buying_power):,.2f} USD")
except Exception as e:
    with col1:
        st.write("⚠️ Konto konnte nicht geladen werden.")
    st.caption(f"Details: {e}")


# ==========================
# Offene Positionen (sicher)
# ==========================
st.subheader("Offene Positionen")

def safe_positions_df() -> pd.DataFrame:
    try:
        positions = api.get_all_positions()
        if not positions:
            return pd.DataFrame(columns=["Symbol", "Qty", "Entry", "Unrealized PnL"])
        rows = []
        for p in positions:
            rows.append(
                {
                    "Symbol": p.symbol,
                    "Qty": float(p.qty),
                    "Entry": float(p.avg_entry_price or 0),
                    "Unrealized PnL": float(p.unrealized_pl or 0),
                }
            )
        return pd.DataFrame(rows)
    except Exception as e:
        st.warning(f"⚠️ Positionen konnten nicht geladen werden: {e}")
        return pd.DataFrame(columns=["Symbol", "Qty", "Entry", "Unrealized PnL"])

pos_df = safe_positions_df()
st.dataframe(pos_df, height=210, width=None, use_container_width=False)


# ==========================
# Watchlist-Signale (robust)
# ==========================
st.subheader("Watchlist-Signale")

# Dynamische Spaltenanzahl (max 4 pro Reihe)
symbols = list(config.SYMBOLS) if hasattr(config, "SYMBOLS") else list(getattr(config, "WATCHLIST", []))
if not symbols:
    st.info("Keine Symbole konfiguriert (config.SYMBOLS ist leer).")
else:
    # 4 Spalten pro Reihe
    per_row = 4
    for i in range(0, len(symbols), per_row):
        row_syms = symbols[i : i + per_row]
        row_cols = st.columns(len(row_syms))
        for c, sym in zip(row_cols, row_syms):
            with c:
                with st.container(border=True):
                    st.markdown(f"**{sym}:**")
                    sig, rsi_val, used_tf, detail = rsi_signal_for_symbol(sym)
                    if rsi_val is not None:
                        st.write(f"RSI: **{rsi_val:.2f}**  •  TF: {used_tf}")
                    else:
                        st.write(f"RSI: —  •  TF: {used_tf}")

                    if sig in ("BUY", "SELL", "HOLD"):
                        st.write(sig)
                    else:
                        st.write(f"⚠️ {sig}")
                        if detail:
                            st.caption(detail)

    st.caption(
        f"Watchlist: {', '.join(symbols)} • Timeframe: {config.TIMEFRAME} "
        f"(Fallback: {config.FALLBACK_TIMEFRAME}) • Feed: {config.API_DATA_FEED} • "
        f"Letzte Aktualisierung: {pd.Timestamp.utcnow():%Y-%m-%d %H:%M:%S} UTC"
    )
