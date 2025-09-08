# streamlit_app.py
import datetime as dt
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

import config  # get_api(), SYMBOLS/WATCHLIST, TIMEFRAME, FALLBACK_TIMEFRAME, API_DATA_FEED, RSI_*

# ---- NEU: v3 Market-Data (alpaca-py) ----
try:
    from alpaca.data import StockHistoricalDataClient, StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    HAVE_V3 = True
except Exception:
    HAVE_V3 = False


# =========================================
# Streamlit-Setup
# =========================================
st.set_page_config(page_title="RSI Mean-Reversion Bot – Aktien-Swing", layout="wide")


# =========================================
# Hilfen: Zeit und Formatierung
# =========================================
def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def fmt_usd(x: float) -> str:
    try:
        return f"{float(x):,.2f} USD"
    except Exception:
        return "-"


# =========================================
# Caches
# =========================================
@st.cache_resource(show_spinner=False)
def get_api():
    return config.get_api()


@st.cache_resource(show_spinner=False)
def get_v3_client():
    """v3 Market-Data Client (alpaca-py)."""
    if not HAVE_V3:
        return None
    from os import getenv
    return StockHistoricalDataClient(getenv("APCA_API_KEY_ID", ""), getenv("APCA_API_SECRET_KEY", ""))


@st.cache_data(show_spinner=False, ttl=60)
def get_account_snapshot() -> Tuple[Optional[dict], Optional[str]]:
    try:
        api = get_api()
        acc = api.get_account()
        data = dict(
            equity=float(getattr(acc, "equity", 0.0)),
            cash=float(getattr(acc, "cash", 0.0)),
            buying_power=float(getattr(acc, "buying_power", 0.0)),
            currency=getattr(acc, "currency", "USD"),
        )
        return data, None
    except Exception as e:
        return None, f"Konto konnte nicht geladen werden: {e}"


# =========================================
# Robuster Positionsabruf
# =========================================
def fetch_positions_safely(api) -> list:
    try:
        if hasattr(api, "get_all_positions"):
            return api.get_all_positions() or []
        if hasattr(api, "list_positions"):
            return api.list_positions() or []
    except Exception:
        pass
    return []


# =========================================
# v3 Bars (Prio 1) + Fallback auf trade_api.get_bars
# =========================================
def _map_timeframe(tf_str: str) -> Optional["TimeFrame"]:
    if not HAVE_V3:
        return None
    s = tf_str.lower()
    if s in ("1day", "1d", "day", "1dayx"):
        return TimeFrame.Day
    if s in ("1hour", "1h", "hour"):
        return TimeFrame.Hour
    if s in ("15min", "15m"):
        return TimeFrame.Minute
    return None


@st.cache_data(show_spinner=False, ttl=60)
def fetch_bars(symbol: str, timeframe: str, limit: int, feed: Optional[str]) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    Holt OHLCV-Bars:
    1) v3 Market-Data (alpaca-py) – stabil & empfohlen
    2) Fallback: alpaca_trade_api.REST.get_bars
    """
    # ---- v3 bevorzugt ----
    v3 = get_v3_client()
    tf = _map_timeframe(timeframe)
    if v3 is not None and tf is not None:
        try:
            req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf, limit=limit)
            bars = v3.get_stock_bars(req)
            df = getattr(bars, "df", None)
            if df is not None and not df.empty:
                # MultiIndex (symbol, timestamp) → auf Symbol filtern
                if isinstance(df.index, pd.MultiIndex):
                    try:
                        df = df.xs(symbol, level=0, drop_level=True)
                    except Exception:
                        pass

                # einheitliche Spalten
                rename_map = {}
                for c in list(df.columns):
                    if c.lower() == "close" or c == "Close":
                        rename_map[c] = "close"
                if rename_map:
                    df = df.rename(columns=rename_map)

                keep = [c for c in df.columns if c.lower() in ("open", "high", "low", "close", "volume", "vwap")]
                if keep:
                    df = df[keep]

                if not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index, utc=True)

                return df.sort_index(), None
        except Exception as e:
            # v3 Fehler → wir probieren fallback
            pass

    # ---- Fallback: trade_api.get_bars ----
    api = get_api()
    err = None
    candidates = []
    if feed:
        candidates.append(lambda: api.get_bars(symbol, timeframe, limit=limit, feed=feed))
        candidates.append(lambda: api.get_bars(symbol, timeframe, feed=feed))
    else:
        candidates.append(lambda: api.get_bars(symbol, timeframe, limit=limit))
        candidates.append(lambda: api.get_bars(symbol, timeframe))

    for caller in candidates:
        try:
            bars = caller()
            df = bars.df if hasattr(bars, "df") else bars
            if df is None or df.empty:
                continue

            if isinstance(df.index, pd.MultiIndex):
                try:
                    df = df.xs(symbol, level=0, drop_level=True)
                except Exception:
                    try:
                        df = df.droplevel(0)
                    except Exception:
                        pass

            if "close" not in [c.lower() for c in df.columns] and "Close" in df.columns:
                df = df.rename(columns={"Close": "close"})

            keep = [c for c in df.columns if c.lower() in ("open", "high", "low", "close", "volume", "vwap")]
            if keep:
                df = df[keep]

            if not isinstance(df.index, pd.DatetimeIndex):
                if "timestamp" in df.columns:
                    df = df.set_index(pd.to_datetime(df["timestamp"], utc=True))
                else:
                    df.index = pd.to_datetime(df.index, utc=True)

            return df.sort_index(), None
        except Exception as e:
            err = str(e)
            continue

    return None, (f"Keine Bars für {symbol} ({timeframe}). Letzter Fehler: {err}" if err else f"Keine Bars für {symbol} ({timeframe}).")


# =========================================
# RSI
# =========================================
def rsi(series: pd.Series, period: int) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < period + 1:
        return pd.Series(dtype=float)
    delta = s.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)

    roll_up = up.ewm(alpha=1 / period, adjust=False).mean()
    roll_down = down.ewm(alpha=1 / period, adjust=False).mean()
    rs = roll_up / roll_down.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    return rsi_series


# =========================================
# Sidebar – Timeframe (fix & ohne Duplikate)
# =========================================
st.sidebar.markdown("### Steuerung")
st.sidebar.markdown("**Timeframe**")

raw_options = [config.FALLBACK_TIMEFRAME, config.TIMEFRAME]
options = []
for o in raw_options:
    if o not in options:
        options.append(o)

index_default = 0
if len(options) == 2 and options[0] != options[1]:
    index_default = 1

tf_choice = st.sidebar.radio("Timeframe", options=options, index=index_default, key="timeframe_radio")

effective_tf = tf_choice
if config.API_DATA_FEED.lower() == "iex" and tf_choice.lower() != config.FALLBACK_TIMEFRAME.lower():
    effective_tf = config.FALLBACK_TIMEFRAME
    st.sidebar.warning("IEX-Feed liefert keine Intraday-Bars. Timeframe wurde auf **1Day** gesetzt.")

if st.sidebar.button("Aktualisieren"):
    st.cache_data.clear()
    st.rerun()


# =========================================
# Header-Metriken
# =========================================
st.title("RSI Mean-Reversion Bot – Aktien-Swing")

acc, acc_err = get_account_snapshot()
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Equity", fmt_usd(acc["equity"]) if acc else "–")
with col2:
    st.metric("Cash", fmt_usd(acc["cash"]) if acc else "–")
with col3:
    st.metric("Buying Power", fmt_usd(acc["buying_power"]) if acc else "–")
if acc_err:
    st.warning(acc_err)


# =========================================
# Offene Positionen
# =========================================
st.subheader("Offene Positionen")
api = get_api()
positions = fetch_positions_safely(api)

if positions:
    rows = []
    for p in positions:
        try:
            rows.append(
                dict(
                    Symbol=getattr(p, "symbol", ""),
                    Qty=float(getattr(p, "qty", 0)),
                    Entry=float(getattr(p, "avg_entry_price", 0)),
                    Unrealized_PnL=float(getattr(p, "unrealized_pl", 0)),
                )
            )
        except Exception:
            continue
    if rows:
        df_pos = pd.DataFrame(rows)
        st.dataframe(df_pos, width="stretch")
    else:
        st.info("Keine offenen Positionen.")
else:
    st.info("Keine offenen Positionen (oder Trading-Endpoint nicht verfügbar).")


# =========================================
# Watchlist-Signale
# =========================================
st.subheader("Watchlist-Signale")

cols = st.columns(len(config.WATCHLIST))
for idx, sym in enumerate(config.WATCHLIST):
    with cols[idx]:
        st.markdown(f"**{sym}:**")
        df, err = fetch_bars(symbol=sym, timeframe=effective_tf, limit=300, feed=config.API_DATA_FEED)

        if df is None or "close" not in df.columns:
            st.write("Keine Daten vom Feed")
            if err:
                st.caption(err)
            continue

        rsi_series = rsi(df["close"], config.RSI_PERIOD)
        if rsi_series.empty:
            st.write("Zu wenige Datenpunkte")
            continue

        last_rsi = float(rsi_series.iloc[-1])
        if last_rsi <= config.RSI_LOWER:
            signal = "BUY"
        elif last_rsi >= config.RSI_UPPER:
            signal = "SELL"
        else:
            signal = "HOLD"

        st.write(f"RSI({config.RSI_PERIOD}): **{last_rsi:.2f}** → **{signal}**")

        small = df[["close"]].tail(10).copy()
        small.index.name = "Zeit"
        small.rename(columns={"close": "Close"}, inplace=True)
        st.dataframe(small, width="stretch")


# =========================================
# Footer
# =========================================
st.caption(
    f"Watchlist: {', '.join(config.WATCHLIST)} • Timeframe: {effective_tf} "
    f"• Feed: {config.API_DATA_FEED.upper()} • Letzte Aktualisierung: {now_utc().strftime('%Y-%m-%d %H:%M:%S')} UTC"
)
