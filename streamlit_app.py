# streamlit_app.py
import time
import pandas as pd
import streamlit as st
import alpaca_trade_api as tradeapi

import config
import control
import strategy  # nutzt: strategy.rsi(series) und strategy.generate_signal_from_df(df)

# -------------------------------------------------------
# Seitensetup
# -------------------------------------------------------
st.set_page_config(page_title="RSI Mean-Reversion – Dashboard", layout="wide")
st.title("RSI Mean-Reversion Bot – Aktien-Swing")

# -------------------------------------------------------
# Sidebar: Steuerung
# -------------------------------------------------------
with st.sidebar:
    st.markdown("### Steuerung")
    paused = control.is_paused()
    st.write(f"Status: **{'AKTIV' if not paused else 'PAUSIERT'}**")

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

# -------------------------------------------------------
# Hilfsfunktionen
# -------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_api():
    # Sanity Check – vermeidet hässlichen Traceback im UI
    if not (config.API_KEY and config.API_SECRET and config.API_BASE_URL):
        st.error(
            "Alpaca API-Keys/URL fehlen. "
            "Setze `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`, `APCA_API_BASE_URL` "
            "in Render → Environment."
        )
        st.stop()
    return tradeapi.REST(
        key_id=config.API_KEY,
        secret_key=config.API_SECRET,
        base_url=config.API_BASE_URL
    )

api = get_api()


def load_bars(symbol: str, limit: int = 200) -> pd.DataFrame:
    """
    Holt Bars für ein einzelnes Symbol und gibt einen DataFrame mit 'close' etc. zurück.
    Behandelt MultiIndex (Alpaca) und konvertiert Zahlen-Spalten.
    """
    df = api.get_bars(symbol, config.TIMEFRAME, limit=limit).df
    if df is None or df.empty:
        return pd.DataFrame()

    # MultiIndex -> nur die Zeilen des Symbols nehmen
    if isinstance(df.index, pd.MultiIndex):
        try:
            df = df.loc[(symbol,), :]
        except Exception:
            # falls Alpaca mal kein Level hat – defensiv weiter
            pass

    # numerische Spalten casten
    for c in ("open", "high", "low", "close", "volume", "vwap"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=["close"])
    return df


# -------------------------------------------------------
# Konto-Infos
# -------------------------------------------------------
try:
    acct = api.get_account()
    c1, c2, c3 = st.columns(3)
    c1.metric("Equity", f"{float(acct.equity):,.2f} {acct.currency}")
    c2.metric("Cash", f"{float(acct.cash):,.2f} USD")
    c3.metric("Buying Power", f"{float(acct.buying_power):,.2f} USD")
except Exception as e:
    st.error(f"Konto-Fehler: {e}")

# -------------------------------------------------------
# Offene Positionen
# -------------------------------------------------------
st.subheader("Offene Positionen")
try:
    pos = api.list_positions()
    if pos:
        st.table(pd.DataFrame([{
            "Symbol": p.symbol,
            "Qty": p.qty,
            "Entry": float(p.avg_entry_price),
            "Unrealized PnL": float(getattr(p, "unrealized_pl", 0.0))
        } for p in pos]))
    else:
        st.write("Keine")
except Exception:
    st.write("Keine")

# -------------------------------------------------------
# Watchlist – Signale & Mini-Charts
# -------------------------------------------------------
st.subheader("Watchlist-Signale")

# Symbole in 3 Spalten verteilen
cols = st.columns(3)

for i, sym in enumerate(config.WATCHLIST):
    col = cols[i % 3]
    with col:
        try:
            df = load_bars(sym, limit=max(100, config.RSI_LEN + 20))
            if df.empty or "close" not in df.columns:
                st.write(f"**{sym}**: Keine Daten")
                continue

            # RSI + Signal berechnen (robust)
            signal = strategy.generate_signal_from_df(df)
            closes = df["close"].astype(float)
            r = strategy.rsi(closes).iloc[-1]

            st.markdown(f"**{sym}** — Signal: `{signal}` • RSI(2): `{r:.1f}`")
            st.line_chart(closes.tail(90))

        except Exception as e:
            st.write(f"**{sym}**: Fehler {e}")

st.caption(
    f"Watchlist: {', '.join(config.WATCHLIST)} • "
    f"Timeframe: {getattr(config.TIMEFRAME, 'name', 'Daily')} • "
    f"Letzte Aktualisierung: {time.strftime('%Y-%m-%d %H:%M:%S')} UTC"
)
