# streamlit_app.py
import datetime as dt
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

import config  # nutzt: get_api(), SYMBOLS/WATCHLIST, TIMEFRAME, FALLBACK_TIMEFRAME, API_DATA_FEED, RSI_*


# =========================================
# Streamlit-Setup
# =========================================
st.set_page_config(page_title="RSI Mean-Reversion Bot – Aktien-Swing", layout="wide")


# =========================================
# Hilfen: Zeit und Formatierung
# =========================================
def now_utc() -> dt.datetime:
    # timezone-aware, ohne Deprecation-Warnung
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


@st.cache_data(show_spinner=False, ttl=60)
def get_account_snapshot() -> Tuple[Optional[dict], Optional[str]]:
    """Liest Konto (equity, cash, buying_power). Gibt (dict|None, error|None) zurück."""
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
    """
    Liefert eine Liste offener Positionen.
    Funktioniert mit unterschiedlichen alpaca-trade-api Versionen.
    """
    try:
        if hasattr(api, "get_all_positions"):
            return api.get_all_positions() or []
        if hasattr(api, "list_positions"):
            return api.list_positions() or []
    except Exception:
        pass
    return []


# =========================================
# Bars laden (robust für API-Signaturen)
# =========================================
@st.cache_data(show_spinner=False, ttl=60)
def fetch_bars_safely(symbol: str, timeframe: str, limit: int, feed: Optional[str]) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    Holt OHLCV-Bars.
    Versucht unterschiedliche Funktionssignaturen der alpaca-trade-api (3.x).
    Gibt (DataFrame|None, error|None) zurück.
    """
    api = get_api()
    err = None

    # Kandidaten-Aufrufe (ohne 'symbols=' – einige Versionen kennen nur 'symbol')
    call_variants = []
    if feed:
        call_variants.append(lambda: api.get_bars(symbol, timeframe, limit=limit, feed=feed))
        call_variants.append(lambda: api.get_bars(symbol, timeframe, feed=feed))  # Fallback ohne limit
    else:
        call_variants.append(lambda: api.get_bars(symbol, timeframe, limit=limit))
        call_variants.append(lambda: api.get_bars(symbol, timeframe))

    for caller in call_variants:
        try:
            bars = caller()
            if bars is None:
                continue

            df = bars.df if hasattr(bars, "df") else bars
            if df is None or len(df) == 0:
                continue

            # MultiIndex (symbol, timestamp) → auf Symbol filtern
            if isinstance(df.index, pd.MultiIndex):
                try:
                    df = df.xs(symbol, level=0, drop_level=True)
                except Exception:
                    # wenn nur 1 Symbol vorhanden ist
                    try:
                        df = df.droplevel(0)
                    except Exception:
                        pass

            # Spalten vereinheitlichen
            rename_map = {}
            if "close" not in [c.lower() for c in df.columns] and "Close" in df.columns:
                rename_map["Close"] = "close"
            if rename_map:
                df = df.rename(columns=rename_map)

            # Nur relevante Spalten
            keep = [c for c in df.columns if c.lower() in ("open", "high", "low", "close", "volume", "vwap")]
            if keep:
                df = df[keep]

            # Index in Zeit
            if not isinstance(df.index, pd.DatetimeIndex):
                if "timestamp" in df.columns:
                    df = df.set_index(pd.to_datetime(df["timestamp"], utc=True))
                else:
                    df.index = pd.to_datetime(df.index, utc=True)

            df = df.sort_index()
            return df, None

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
# Sidebar – Timeframe (mit Label & De-Dupe)
# =========================================
st.sidebar.markdown("### Steuerung")
st.sidebar.markdown("**Timeframe**")

# Optionen erstellen und Duplikate entfernen
raw_options = [config.FALLBACK_TIMEFRAME, config.TIMEFRAME]
options = []
for o in raw_options:
    if o not in options:
        options.append(o)

# Index-Logik: wenn 2 unterschiedliche Werte → bevorzugt TIMEFRAME (Index 1),
# sonst nur eine Option (Index 0)
index_default = 0
if len(options) == 2 and options[0] != options[1]:
    index_default = 1  # TIMEFRAME steht als 2. in raw_options

tf_choice = st.sidebar.radio(
    "Timeframe",
    options=options,
    index=index_default,
    key="timeframe_radio",
)

effective_tf = tf_choice
# IEX hat keine Intraday-Bars → zurück auf 1Day
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
        df, err = fetch_bars_safely(symbol=sym, timeframe=effective_tf, limit=300, feed=config.API_DATA_FEED)

        if df is None or "close" not in df.columns:
            st.write("Keine Daten vom Feed")
            if err:
                st.caption(err)
            continue

        # RSI berechnen
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

        # Kleine Tabelle der letzten Close-Werte
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
