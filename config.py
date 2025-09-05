# config.py
import os
import alpaca_trade_api as tradeapi
import streamlit as st

# ================================
# API-Konfiguration (ENV Variablen)
# ================================
API_KEY = os.getenv("APCA_API_KEY_ID", "")
API_SECRET = os.getenv("APCA_API_SECRET_KEY", "")
API_BASE_URL = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")

# Datenfeed aus ENV (Standard: "iex"), nur iex/sip zulassen
API_DATA_FEED: str = os.getenv("APCA_API_DATA_FEED", "iex").lower()
if API_DATA_FEED not in {"iex", "sip"}:
    API_DATA_FEED = "iex"

# Alias für die App (die App erwartet DATA_FEED)
DATA_FEED = API_DATA_FEED

# ================================
# Strategie-Parameter
# ================================
# Watchlist / Symbole
SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT"]
# Rückwärtskompatibler Alias
WATCHLIST = SYMBOLS

# Standard-Zeitrahmen (für das Dashboard: Daily empfohlen)
# Wenn du lieber Intraday nutzen willst, setze TIMEFRAME = "1Hour"
TIMEFRAME = "1Day"
FALLBACK_TIMEFRAME = "1Day"  # bleibt für andere Komponenten nutzbar

# RSI-Einstellungen
RSI_PERIOD = 14
RSI_LOWER = 30
RSI_UPPER = 70

# Risiko- & Positions-Parameter (für einen Trading-Worker; Dashboard nutzt sie nicht direkt)
MAX_TRADE_USD = 2000.0
STOP_LOSS_PCT = 0.03    # 3%
TAKE_PROFIT_PCT = 0.06  # 6%

# Bot-Loop (nur relevant für einen Worker/Daemon)
LOOP_SECONDS = 60 * 5  # alle 5 Minuten

# ================================
# Alpaca REST-Client (gecached)
# ================================
@st.cache_resource(show_spinner=False)
def get_api():
    if not (API_KEY and API_SECRET and API_BASE_URL):
        raise ValueError(
            "❌ Alpaca API Keys oder Base URL fehlen! "
            "Bitte APCA_API_KEY_ID, APCA_API_SECRET_KEY und APCA_API_BASE_URL setzen."
        )
    return tradeapi.REST(
        key_id=API_KEY,
        secret_key=API_SECRET,
        base_url=API_BASE_URL,
        api_version="v2",
    )
