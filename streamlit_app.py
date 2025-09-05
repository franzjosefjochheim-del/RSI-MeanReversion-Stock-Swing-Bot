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

# Datenfeed: standardmäßig "iex", nur "iex" oder "sip" erlaubt
API_DATA_FEED: str = os.getenv("APCA_API_DATA_FEED", "iex").lower()
if API_DATA_FEED not in ["iex", "sip"]:
    API_DATA_FEED = "iex"

# ================================
# Strategie-Parameter
# ================================
# Deine Watchlist / Symbole
SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT"]

# Alias für Rückwärtskompatibilität (manche UIs nutzen WATCHLIST)
WATCHLIST = SYMBOLS

# Standard-Zeitrahmen + Fallback (wenn 1h keine Daten liefert)
TIMEFRAME = "1Hour"
FALLBACK_TIMEFRAME = "1Day"

# RSI-Einstellungen
RSI_PERIOD = 14
RSI_LOWER = 30
RSI_UPPER = 70

# Risiko- & Positions-Parameter
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
