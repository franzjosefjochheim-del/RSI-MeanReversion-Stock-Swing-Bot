# streamlit_app.py
import time
from typing import List, Tuple, Optional

import pandas as pd
import streamlit as st
import alpaca_trade_api as tradeapi  # nur für Typ-Hinweis

import config  # deine config.py mit get_api(), SYMBOLS/WATCHLIST etc.


# -----------------------------
# Streamlit – Seitengrundlagen
# -----------------------------
st.set_page_config(page_title="RSI Mean-Reversion Bot – Aktien-Swing", layout="wide")
st.title("RSI Mean-Reversion Bot – Aktien-Swing")

with st.sidebar:
    st.markdown("### Steuerung")
    st.write(f"Status: **AKTIV**")
    if st.button("Aktualisieren"):
        st.rerun()


# -----------------------------
# Hilfsfunktionen (robust)
# -----------------------------

@st.cache_resource(show_spinner=False)
def get_api() -> tradeapi.REST:
    """Gecachter Alpaca-Client aus config.get_api()."""
    return config.get_api()


def list_positions_safe(api: tradeapi.REST):
    """
    Robust alle offenen Positionen holen – je nach SDK-Version heißen die
    Methoden anders.
    """
    for meth in ("get_all_positions", "list_positions", "get_positions"):
        if hasattr(api, meth):
            try:
                return getattr(api, meth)()
            except Exception:
                pass
    return []


@st.cache_data(show_spinner=False, ttl=60)
def fetch_bars(
    symbol: str,
    timeframe: str,
    limit: int = 300,
    feed: Optional[str] = None,
) -> pd.DataFrame:
    """
    Bars mit der aktuellen Alpaca-Signatur laden:
      get_bars(symbol, timeframe, *, start=None, end=None, limit=None, feed=None)
    WICHTIG: 'symbols' gibt es nicht mehr – erster Parameter ist das Symbol!
    """
    api = get_api()

    # Manche Lib-Versionen nennen das Enum "TimeFrame", aber String funktioniert auch.
    try:
        df = api.get_bars(symbol, timeframe, limit=limit, feed=feed).df
    except TypeError:
        # Falls eine ältere Signatur meckert, versuchen wir ohne 'feed'
        df = api.get_bars(symbol, timeframe, limit=limit).df

    # Bei MultiIndex (symbol, timestamp) auf ein Symbol herunterbrechen
    if isinstance(df.index, pd.MultiIndex):
        try:
            df = df.loc[(symbol,), :].copy()
        except KeyError:
            # Keine Zeilen für dieses Symbol
            df = pd.DataFrame()

    # Normiere Spaltennamen auf lower-case
    if not df.empty:
        df = df.copy()
        df.columns = [c.lower() for c in df.columns]
        # Sicherstellen, dass close numerisch ist
        if "close" in df.columns:
            df["close"] = pd.to_numeric(df["close"], errors="coerce")
            df = df.dropna(subset=["close"])

    return df


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Standard-RSI."""
    if series is None or series.empty:
        return pd.Series(dtype=float)
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    roll_up = up.ewm(alpha=1 / period, adjust=False).mean()
    roll_down = down.ewm(alpha=1 / period, adjust=False).mean()
    rs = roll_up / roll_down
    return 100 - (100 / (1 + rs))


def compute_signal(df: pd.DataFrame) -> Optional[str]:
    """RSI-Signal (BUY/SELL/HOLD) aus DataFrame (benötigt Spalte 'close')."""
    if df is None or df.empty or "close" not in df.columns:
        return None
    r = rsi(df["close"], config.RSI_PERIOD)
    if r.empty:
        return None
    last = r.iloc[-1]
    if last <= config.RSI_LOWER:
        return "BUY"
    if last >= config.RSI_UPPER:
        return "SELL"
    return "HOLD"


def rsi_with_fallback(
    symbol: str,
    primary_tf: str,
    fallback_tf: str,
    feed: str,
    min_points: int = 20,
) -> Tuple[str, Optional[float], str]:
    """
    RSI + Signal mit Fallback-Zeitrahmen.
    Rückgabe: (SignalText, letzterRSI, verwendeterTF)
    """
    # 1) Primär versuchen
    df = fetch_bars(symbol, primary_tf, limit=300, feed=feed)
    used_tf = primary_tf

    if df is None or df.empty or len(df.index) < min_points:
        # 2) Fallback
        df = fetch_bars(symbol, fallback_tf, limit=300, feed=feed)
        used_tf = fallback_tf

    if df is None or df.empty or "close" not in df.columns:
        return ("Keine Daten vom Feed", None, used_tf)

    r = rsi(df["close"], config.RSI_PERIOD)
    if r.empty:
        return ("Zu wenige Datenpunkte", None, used_tf)

    last_rsi = float(r.iloc[-1])
    sig = "HOLD"
    if last_rsi <= config.RSI_LOWER:
        sig = "BUY"
    elif last_rsi >= config.RSI_UPPER:
        sig = "SELL"

    return (sig, last_rsi, used_tf)


# --------------------------------
# Konto-Kennzahlen + Positions-Tbl
# --------------------------------
api = get_api()
account = api.get_account()
col1, col2, col3 = st.columns(3)
col1.metric("Equity", f"{float(account.equity):,.2f} USD")
col2.metric("Cash", f"{float(account.cash):,.2f} USD")
col3.metric("Buying Power", f"{float(account.buying_power):,.2f} USD")

st.markdown("### Offene Positionen")

# Positionen robust laden
positions = []
try:
    positions = list_positions_safe(api)
except Exception as e:
    st.warning(f"Positionen konnten nicht geladen werden: {e}")

pos_rows = []
for p in positions or []:
    try:
        pos_rows.append(
            {
                "Symbol": getattr(p, "symbol", ""),
                "Qty": float(getattr(p, "qty", 0)),
                "Entry": float(getattr(p, "avg_entry_price", 0.0)),
                "Unrealized PnL": float(getattr(p, "unrealized_pl", 0.0)),
            }
        )
    except Exception:
        pass

pos_df = pd.DataFrame(pos_rows, columns=["Symbol", "Qty", "Entry", "Unrealized PnL"])
st.dataframe(pos_df, use_container_width=True)


# -----------------------------
# Watchlist – RSI Signale
# -----------------------------
st.markdown("### Watchlist-Signale")

symbols: List[str] = getattr(config, "WATCHLIST", None) or getattr(config, "SYMBOLS", [])
if not symbols:
    st.info("Keine Symbole in WATCHLIST/SYMBOLS definiert.")
else:
    cols = st.columns(len(symbols))
    for i, sym in enumerate(symbols):
        with cols[i]:
            st.markdown(f"**{sym}:**")
            try:
                signal_txt, last_rsi, used_tf = rsi_with_fallback(
                    symbol=sym,
                    primary_tf=config.TIMEFRAME,
                    fallback_tf=config.FALLBACK_TIMEFRAME,
                    feed=getattr(config, "API_DATA_FEED", "iex"),
                )
                if last_rsi is None:
                    st.write(signal_txt)
                else:
                    st.write(f"RSI: **{last_rsi:.1f}** – TF: **{used_tf}**")
                    st.write(f"Signal: **{signal_txt}**")
            except Exception as e:
                st.warning(f"Fehler bei {sym}: {e}")

st.caption(
    f"Watchlist: {', '.join(symbols)} • Timeframe: {config.TIMEFRAME} "
    f"(Fallback: {config.FALLBACK_TIMEFRAME}) • Feed: {getattr(config, 'API_DATA_FEED', 'iex')} • "
    f"Letzte Aktualisierung: {pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
)
