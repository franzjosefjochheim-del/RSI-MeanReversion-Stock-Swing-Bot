# streamlit_app.py
import time
import pandas as pd
import numpy as np
import streamlit as st

import config  # unsere zentrale Konfiguration
import alpaca_trade_api as tradeapi


# ----------------------------
# Hilfen / Fallbacks aus config
# ----------------------------
WATCHLIST = getattr(
    config, "WATCHLIST",
    getattr(config, "SYMBOLS", ["SPY", "QQQ", "AAPL", "MSFT"])
)
TIMEFRAME = getattr(config, "TIMEFRAME", "1Hour")
FALLBACK_TIMEFRAME = getattr(config, "FALLBACK_TIMEFRAME", "1Day")
FEED = getattr(config, "API_DATA_FEED", "iex")

RSI_PERIOD = getattr(config, "RSI_PERIOD", 14)
RSI_LOWER = getattr(config, "RSI_LOWER", 30)
RSI_UPPER = getattr(config, "RSI_UPPER", 70)


# ----------------------------
# API-Client (aus config)
# ----------------------------
@st.cache_resource(show_spinner=False)
def get_api():
    # bevorzuge den in config gecachten Client
    if hasattr(config, "get_api"):
        return config.get_api()
    # Fallback: direkter Aufbau (sollte nicht nötig sein)
    return tradeapi.REST(
        key_id=config.API_KEY,
        secret_key=config.API_SECRET,
        base_url=config.API_BASE_URL,
        api_version="v2",
    )


api = get_api()


# ----------------------------
# UI Kopf
# ----------------------------
st.set_page_config(page_title="RSI Mean-Reversion Bot – Aktien-Swing", layout="wide")
st.title("RSI Mean-Reversion Bot – Aktien-Swing")

# Sidebar Steuerung
with st.sidebar:
    st.markdown("### Steuerung")
    st.write("Status: **AKTIV**")
    colA, colB = st.columns(2)
    if colA.button("Aktualisieren"):
        st.rerun()
    st.button("Pause", help="Nur Anzeige, kein echter Stop-Schalter in diesem Dashboard.")


# ----------------------------
# Kontoinformation
# ----------------------------
def load_account_metrics():
    try:
        acct = api.get_account()
        equity = float(getattr(acct, "equity", 0) or 0)
        cash = float(getattr(acct, "cash", 0) or 0)
        buying_power = float(getattr(acct, "buying_power", 0) or 0)
        return equity, cash, buying_power
    except Exception as e:
        st.warning(f"Account konnte nicht geladen werden: {e}")
        return 0.0, 0.0, 0.0


equity, cash, buying_power = load_account_metrics()
c1, c2, c3 = st.columns(3)
c1.metric("Equity", f"{equity:,.2f} USD")
c2.metric("Cash", f"{cash:,.2f} USD")
c3.metric("Buying Power", f"{buying_power:,.2f} USD")


# ----------------------------
# Offene Positionen
# ----------------------------
def load_positions_df():
    try:
        # Lib-Versionen variieren: list_positions() (neu) oder get_all_positions() (älter)
        if hasattr(api, "list_positions"):
            pos = api.list_positions()
        else:
            pos = api.get_all_positions()
        rows = []
        for p in pos:
            rows.append({
                "Symbol": p.symbol,
                "Qty": float(getattr(p, "qty", 0) or 0),
                "Entry": float(getattr(p, "avg_entry_price", 0) or 0),
                "Unrealized PnL": float(getattr(p, "unrealized_pl", 0) or 0),
            })
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Symbol", "Qty", "Entry", "Unrealized PnL"])
    except Exception as e:
        st.error(f"Positionen konnten nicht geladen werden: {e}")
        return pd.DataFrame(columns=["Symbol", "Qty", "Entry", "Unrealized PnL"])


st.subheader("Offene Positionen")
pos_df = load_positions_df()
st.dataframe(pos_df, use_container_width=False, width="stretch")


# ----------------------------
# Daten holen (Bars) mit Fallback
# ----------------------------
def get_bars_with_fallback(symbol: str, limit: int = 300) -> pd.DataFrame:
    """
    Holt Bars über den Aktien-API-Endpunkt. Nutzt TIMEFRAME, fallbackt auf FALLBACK_TIMEFRAME,
    erzwingt 'symbol'-Spalte und sortiert chronologisch.
    """
    for tf in [TIMEFRAME, FALLBACK_TIMEFRAME]:
        try:
            df = api.get_bars(
                symbol,
                tf,
                limit=limit,
                feed=FEED
            ).df
            if df is None or df.empty:
                continue
            # Multi-Index -> auflösen
            if hasattr(df.index, "names") and df.index.names and df.index.names[0] == "symbol":
                try:
                    df = df.xs(symbol, level="symbol")
                except Exception:
                    pass
            df = df.sort_index()
            df["symbol"] = symbol
            return df
        except Exception:
            continue
    return pd.DataFrame()


# ----------------------------
# RSI-Berechnung
# ----------------------------
def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    roll_up = up.ewm(span=period, adjust=False).mean()
    roll_down = down.ewm(span=period, adjust=False).mean()
    rs = roll_up / (roll_down.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    return rsi


# ----------------------------
# Watchlist-Signale
# ----------------------------
st.subheader("Watchlist-Signale")

if not isinstance(WATCHLIST, (list, tuple)) or len(WATCHLIST) == 0:
    st.info("Keine Watchlist in der Konfiguration gefunden.")
else:
    cols = st.columns(len(WATCHLIST))
    any_data = False

    for i, sym in enumerate(WATCHLIST):
        with cols[i]:
            st.markdown(f"**{sym}:**")
            bars = get_bars_with_fallback(sym, limit=max(200, RSI_PERIOD * 5))

            if bars.empty or "close" not in bars:
                st.write("Keine Daten vom Feed")
                continue

            any_data = True
            closes = pd.to_numeric(bars["close"], errors="coerce").dropna()
            if closes.size < RSI_PERIOD + 5:
                st.write("Zu wenige Datenpunkte")
                continue

            rsi = compute_rsi(closes, RSI_PERIOD)
            last_rsi = float(rsi.iloc[-1])

            if last_rsi < RSI_LOWER:
                st.success(f"RSI {last_rsi:.1f} → **BUY** (überverkauft)")
            elif last_rsi > RSI_UPPER:
                st.error(f"RSI {last_rsi:.1f} → **SELL** (überkauft)")
            else:
                st.write(f"RSI {last_rsi:.1f} → **HOLD**")

    if not any_data:
        st.caption(f"Watchlist: {', '.join(WATCHLIST)} • Timeframe: {TIMEFRAME} • Feed: {FEED}")

st.caption(f"Letzte Aktualisierung: {time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
