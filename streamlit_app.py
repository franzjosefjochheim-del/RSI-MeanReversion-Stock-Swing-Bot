import streamlit as st
import pandas as pd
import alpaca_trade_api as tradeapi
import datetime as dt
import config
import control

# ---------------------------------------------------
# Streamlit Setup
# ---------------------------------------------------
st.set_page_config(page_title="RSI Mean-Reversion Bot – Aktien-Swing", layout="wide")
st.title("RSI Mean-Reversion Bot – Aktien-Swing")

# ---------------------------------------------------
# Sidebar Steuerung
# ---------------------------------------------------
with st.sidebar:
    st.markdown("### Steuerung")
    paused = control.is_paused()
    st.write(f"Status: **{'PAUSIERT' if paused else 'AKTIV'}**")
    colA, colB = st.columns(2)
    if colA.button("Aktualisieren"):
        st.rerun()
    if not paused:
        if colB.button("Pause"):
            control.set_paused(True)
            st.success("Bot pausiert.")
            st.rerun()
    else:
        if colB.button("Start"):
            control.set_paused(False)
            st.success("Bot gestartet.")
            st.rerun()

# ---------------------------------------------------
# Alpaca API Client
# ---------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_api():
    return tradeapi.REST(
        key_id=config.API_KEY,
        secret_key=config.API_SECRET,
        base_url=config.API_BASE_URL,
        api_version="v2"
    )

api = get_api()

# ---------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------
def load_account(api):
    try:
        acct = api.get_account()
        return {
            "Equity": float(acct.equity),
            "Cash": float(acct.cash),
            "Buying Power": float(acct.buying_power),
        }
    except Exception as e:
        st.error(f"Fehler beim Laden des Accounts: {e}")
        return {"Equity": 0, "Cash": 0, "Buying Power": 0}


def load_positions(api):
    """Alle offenen Positionen laden"""
    try:
        positions = api.list_positions()
        rows = []
        for p in positions:
            rows.append({
                "Symbol": p.symbol,
                "Qty": float(p.qty),
                "Entry": float(p.avg_entry_price) if p.avg_entry_price else None,
                "Unrealized PnL": float(p.unrealized_pl) if p.unrealized_pl else None,
            })
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Symbol", "Qty", "Entry", "Unrealized PnL"])
    except Exception as e:
        st.warning(f"Positionen konnten nicht geladen werden: {e}")
        return pd.DataFrame(columns=["Symbol", "Qty", "Entry", "Unrealized PnL"])


def load_bars(api, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
    """Kursdaten holen (MultiIndex beachten)"""
    try:
        df = api.get_bars([symbol], timeframe, limit=limit, feed=config.API_DATA_FEED).df
        if isinstance(df.index, pd.MultiIndex):
            df = df.loc[(symbol,), :]
        if df.empty:
            raise ValueError("Leerer DataFrame vom Feed")
        return df
    except Exception as e:
        st.write(f"**{symbol}:** Keine Daten vom Feed ({e})")
        return pd.DataFrame()


def calc_rsi(prices: pd.Series, period: int = 14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# ---------------------------------------------------
# Account Anzeige
# ---------------------------------------------------
acct = load_account(api)
col1, col2, col3 = st.columns(3)
col1.metric("Equity", f"{acct['Equity']:.2f} USD")
col2.metric("Cash", f"{acct['Cash']:.2f} USD")
col3.metric("Buying Power", f"{acct['Buying Power']:.2f} USD")

# ---------------------------------------------------
# Offene Positionen
# ---------------------------------------------------
st.subheader("Offene Positionen")
positions = load_positions(api)
if not positions.empty:
    st.dataframe(positions, use_container_width=True)
else:
    st.write("Keine offenen Positionen")

# ---------------------------------------------------
# Watchlist & RSI-Signale
# ---------------------------------------------------
st.subheader("Watchlist-Signale")

cols = st.columns(len(config.WATCHLIST))
for i, sym in enumerate(config.WATCHLIST):
    df = load_bars(api, sym, config.TIMEFRAME, limit=200)
    with cols[i]:
        st.markdown(f"**{sym}:**")
        if df.empty:
            st.write("Keine Daten vom Feed")
        else:
            closes = df["close"].astype(float)
            rsi = calc_rsi(closes)
            last_rsi = rsi.iloc[-1]

            if last_rsi < config.RSI_LOWER:
                signal = f"BUY (RSI {last_rsi:.1f})"
            elif last_rsi > config.RSI_UPPER:
                signal = f"SELL (RSI {last_rsi:.1f})"
            else:
                signal = f"HOLD (RSI {last_rsi:.1f})"

            st.write(signal)

# ---------------------------------------------------
# Footer
# ---------------------------------------------------
st.markdown(
    f"Watchlist: {', '.join(config.WATCHLIST)} • "
    f"Timeframe: {config.TIMEFRAME} • Feed: {config.API_DATA_FEED.upper()} • "
    f"Letzte Aktualisierung: {dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
)
