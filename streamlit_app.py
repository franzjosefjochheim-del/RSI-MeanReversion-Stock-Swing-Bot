import time
import pandas as pd
import streamlit as st
import alpaca_trade_api as tradeapi

import config
import control
import strategy

st.set_page_config(page_title="RSI Swing Dashboard", layout="wide")
st.title("RSI Mean-Reversion Bot – Aktien-Swing")

# Sidebar Steuerung
with st.sidebar:
    st.markdown("### Steuerung")
    paused = control.is_paused()
    st.write(f"Status: **{'PAUSIERT' if paused else 'AKTIV'}**")
    colA, colB = st.columns(2)
    if colA.button("Aktualisieren"): st.rerun()
    if not paused:
        if colB.button("Pause"): control.set_paused(True); st.success("Pausiert."); st.rerun()
    else:
        if colB.button("Start"): control.set_paused(False); st.success("Gestartet."); st.rerun()

@st.cache_resource(show_spinner=False)
def get_api():
    return tradeapi.REST(
        key_id=config.API_KEY,
        secret_key=config.API_SECRET,
        base_url=config.API_BASE_URL
    )

api = get_api()

def bars(sym, limit=120):
    df = api.get_bars(sym, config.TIMEFRAME, limit=limit).df
    if isinstance(df.index, pd.MultiIndex):
        df = df.loc[(sym,), :]
    for c in ("open","high","low","close","volume","vwap"):
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["close"])

# Konto
try:
    acct = api.get_account()
    c1, c2, c3 = st.columns(3)
    c1.metric("Equity", f"{float(acct.equity):,.2f} {acct.currency}")
    c2.metric("Cash", f"{float(acct.cash):,.2f} USD")
    c3.metric("Buying Power", f"{float(acct.buying_power):,.2f} USD")
except Exception as e:
    st.error(f"Konto-Fehler: {e}")

# Offene Positionen
st.subheader("Offene Positionen")
try:
    pos = api.list_positions()
    if pos:
        st.table(pd.DataFrame([{
            "Symbol": p.symbol, "Qty": p.qty, "Entry": float(p.avg_entry_price),
            "Unrealized PnL": float(p.unrealized_pl)
        } for p in pos]))
    else:
        st.write("Keine")
except Exception:
    st.write("Keine")

# Watchlist Signale + Charts
st.subheader("Watchlist-Signale")
sym_cols = st.columns(3)
for i, sym in enumerate(config.WATCHLIST):
    try:
        df = bars(sym, limit=60)
        sig = strategy.generate_signal_from_df(df)
        # Mini-Chart
        closes = df["close"].astype(float)
        r = strategy.rsi(closes).iloc[-1]
        with sym_cols[i % 3]:
            st.markdown(f"**{sym}** — Signal: `{sig}`  •  RSI(2): `{r:.1f}`")
            st.line_chart(closes.tail(90))
    except Exception as e:
        with sym_cols[i % 3]:
            st.write(f"{sym}: Fehler {e}")

st.caption(f"Watchlist: {', '.join(config.WATCHLIST)} • Timeframe: Daily • Letzte Aktualisierung: {time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
