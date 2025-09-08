# streamlit_app.py
import datetime as dt
from typing import Tuple, Optional

import numpy as np
import pandas as pd
import streamlit as st

import config  # <- deine config.py

# ===============================
# Seiten-Setup & Sidebar-Steuerung
# ===============================

st.set_page_config(
    page_title="RSI Mean-Reversion Bot – Aktien-Swing",
    layout="wide",
)

st.title("RSI Mean-Reversion Bot – Aktien-Swing")

with st.sidebar:
    st.markdown("### Steuerung")

    # Timeframe-Auswahl (Radio)
    if "tf" not in st.session_state:
        st.session_state.tf = config.TIMEFRAME

    tf_choice = st.radio(
        "Timeframe",
        options=["1Day", "1Hour"],
        index=0 if st.session_state.tf == "1Day" else 1,
    )

    # Wenn Feed IEX und Nutzer 1Hour wählt -> auf 1Day switchen
    effective_tf = tf_choice
    if config.API_DATA_FEED == "iex" and tf_choice != "1Day":
        st.warning(
            "IEX-Feed liefert keine Intraday-Bars. Timeframe wurde auf **1Day** gesetzt."
        )
        effective_tf = "1Day"

    st.session_state.tf = effective_tf

    # Manueller Refresh
    if st.button("Aktualisieren"):
        st.rerun()

# ===============================
# Hilfsfunktionen
# ===============================

@st.cache_resource(show_spinner=False)
def _get_api():
    return config.get_api()

def _now_utc() -> dt.datetime:
    return dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)

def fetch_account(api) -> Tuple[float, float, float, str]:
    """Account-Metriken holen: Equity, Cash, Buying Power, Currency."""
    acct = api.get_account()
    equity = float(acct.equity or 0)
    cash = float(acct.cash or 0)
    buying_power = float(acct.buying_power or 0)
    ccy = getattr(acct, "currency", "USD") or "USD"
    return equity, cash, buying_power, ccy

def fetch_positions(api) -> pd.DataFrame:
    """Offene Positionen (Symbol, Qty, Entry, UPL)."""
    try:
        # In neueren alpaca_trade_api Versionen: get_positions()
        positions = api.get_positions()
    except AttributeError:
        # Fallback (ältere Versionen): get_all_positions()
        positions = api.get_all_positions()

    rows = []
    for p in positions:
        try:
            rows.append(
                {
                    "Symbol": p.symbol,
                    "Qty": float(p.qty),
                    "Entry": float(p.avg_entry_price or 0),
                    "Unrealized PnL": float(p.unrealized_pl or 0),
                }
            )
        except Exception:
            pass

    df = pd.DataFrame(rows, columns=["Symbol", "Qty", "Entry", "Unrealized PnL"])
    return df.sort_values("Symbol") if not df.empty else df

def fetch_bars(api, symbol: str, timeframe: str, limit: int = 300) -> Optional[pd.DataFrame]:
    """
    Holt Bars je Symbol & Timeframe (Einzelsymbol!).
    Nutzt den in config gesetzten Feed (iex/sip).
    Gibt DataFrame mit Spalten ['open','high','low','close','volume','timestamp'] zurück.
    """
    try:
        bars = api.get_bars(symbol, timeframe, limit=limit, feed=config.API_DATA_FEED)
    except TypeError:
        # Für ältere SDK-Signaturen (ohne 'feed')
        bars = api.get_bars(symbol, timeframe, limit=limit)

    if bars is None:
        return None

    # Die Bibliothek liefert je nach Version BarSet, DataFrame oder Liste.
    # Versuche robust zu normalisieren:
    if isinstance(bars, pd.DataFrame):
        df = bars.copy()
    else:
        try:
            df = bars.df  # BarSet -> DataFrame (bei manchen Versionen)
        except Exception:
            # Manuelle Konvertierung: iterieren und records bauen
            records = []
            for b in bars:
                records.append(
                    {
                        "timestamp": getattr(b, "t", getattr(b, "timestamp", None)),
                        "open": float(getattr(b, "o", getattr(b, "open", 0)) or 0),
                        "high": float(getattr(b, "h", getattr(b, "high", 0)) or 0),
                        "low": float(getattr(b, "l", getattr(b, "low", 0)) or 0),
                        "close": float(getattr(b, "c", getattr(b, "close", 0)) or 0),
                        "volume": float(getattr(b, "v", getattr(b, "volume", 0)) or 0),
                    }
                )
            df = pd.DataFrame.from_records(records)

    # Index/Spalten aufräumen
    if "symbol" in df.columns:
        # Multi-Symbol Index entfernen, falls vorhanden
        try:
            df = df.xs(symbol, level="symbol")
        except Exception:
            pass

    # Einheitliche Timestamp-Spalte
    if "timestamp" not in df.columns:
        if "t" in df.columns:
            df = df.rename(columns={"t": "timestamp"})
        elif "time" in df.columns:
            df = df.rename(columns={"time": "timestamp"})

    # Nur relevante Spalten behalten (falls vorhanden)
    keep_cols = [c for c in ["open", "high", "low", "close", "volume", "timestamp"] if c in df.columns]
    df = df[keep_cols].copy()

    # Chronologisch sortieren
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp")

    return df if not df.empty else None

def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Klassischer RSI (Wilder)."""
    delta = close.diff()
    gain = delta.where(delta > 0.0, 0.0)
    loss = -delta.where(delta < 0.0, 0.0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / (avg_loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)

def rsi_signal(df: pd.DataFrame) -> Optional[Tuple[float, str]]:
    """RSI berechnen & einfaches Signal bestimmen (BUY/SELL/HOLD)."""
    if df is None or df.empty or "close" not in df.columns:
        return None
    rsi = compute_rsi(df["close"].astype(float), period=config.RSI_PERIOD)
    last = float(rsi.iloc[-1]) if len(rsi) else None
    if last is None:
        return None
    if last < config.RSI_LOWER:
        sig = "BUY"
    elif last > config.RSI_UPPER:
        sig = "SELL"
    else:
        sig = "HOLD"
    return last, sig

# ===============================
# Daten laden
# ===============================

api = _get_api()

# Account-KPIs
equity, cash, buying_power, ccy = fetch_account(api)

c1, c2, c3 = st.columns(3)
c1.metric("Equity", f"{equity:,.2f} {ccy}")
c2.metric("Cash", f"{cash:,.2f} {ccy}")
c3.metric("Buying Power", f"{buying_power:,.2f} {ccy}")

# Positionen
st.subheader("Offene Positionen")
pos_df = pd.DataFrame()
pos_error = None
try:
    pos_df = fetch_positions(api)
except Exception as e:
    pos_error = str(e)

if pos_error:
    st.warning(f"Positionen konnten nicht geladen werden: {pos_error}")

if pos_df.empty:
    # Leere Tabelle in passabler Breite anzeigen
    st.dataframe(pd.DataFrame(columns=["Symbol", "Qty", "Entry", "Unrealized PnL"]), use_container_width=True)
else:
    st.dataframe(pos_df, use_container_width=True)

# ===============================
# Watchlist-Signale
# ===============================

st.subheader("Watchlist-Signale")

symbols = getattr(config, "WATCHLIST", getattr(config, "SYMBOLS", ["SPY", "QQQ", "AAPL", "MSFT"]))
n = max(1, len(symbols))
cols = st.columns(min(4, n))  # bis zu 4 Spalten nebeneinander

for i, sym in enumerate(symbols):
    col = cols[i % len(cols)]
    with col:
        st.markdown(f"**{sym}:**")
        # Bars holen mit ausgewähltem Timeframe (ggf. Auto-Fallback in der Sidebar bereits gesetzt)
        tf = st.session_state.tf

        df_day = fetch_bars(api, sym, tf, limit=300)

        if df_day is None or df_day.empty:
            st.write("Keine Daten vom Feed")
            continue

        rs = rsi_signal(df_day)
        if rs is None:
            st.write("Kein DataFrame oder 'close' fehlt")
        else:
            rsi_val, sig = rs
            st.write(f"RSI: **{rsi_val:.1f}**  •  Signal: **{sig}**")

# Footer / Meta
st.caption(
    f"Watchlist: {', '.join(symbols)} • Timeframe: {st.session_state.tf} "
    f"• Feed: {config.API_DATA_FEED} • Letzte Aktualisierung: {_now_utc().strftime('%Y-%m-%d %H:%M:%S')} UTC"
)
