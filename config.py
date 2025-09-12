# config.py
import os
import streamlit as st

# ================================
# Alpaca Keys & Endpunkte
# ================================
API_KEY = os.getenv("APCA_API_KEY_ID", "")
API_SECRET = os.getenv("APCA_API_SECRET_KEY", "")
API_BASE_URL = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")

# Datenfeed (iex oder sip); Default = iex
API_DATA_FEED = os.getenv("APCA_API_DATA_FEED", "iex").lower()
if API_DATA_FEED not in {"iex", "sip"}:
    API_DATA_FEED = "iex"

# ================================
# Strategie-Parameter
# ================================
SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT"]   # Watchlist
WATCHLIST = SYMBOLS                        # Alias für Rückwärtskompatibilität

# IEX liefert im Paper-Plan keine Intraday-Bars → 1Day als Standard
TIMEFRAME = "1Day"
FALLBACK_TIMEFRAME = "1Day"

# RSI
RSI_PERIOD = 14
RSI_LOWER = 30
RSI_UPPER = 70

# Risiko- & Positions-Parameter
MAX_TRADE_USD = 2000.0
STOP_LOSS_PCT = 0.03
TAKE_PROFIT_PCT = 0.06

# Bot-Loop (falls du später einen Worker baust)
LOOP_SECONDS = 60 * 5

# ================================
# Trading-Client (nur falls Orders benötigt)
# ================================
try:
    import alpaca_trade_api as tradeapi  # optional
except Exception:
    tradeapi = None

@st.cache_resource(show_spinner=False)
def get_trading_api():
    """
    Trading-Client aus alpaca_trade_api (nur nötig, wenn du Orders platzierst).
    """
    if tradeapi is None:
        raise RuntimeError(
            "alpaca_trade_api ist nicht installiert. "
            "Füge es in requirements.txt hinzu, wenn du Orders platzieren willst."
        )
    if not (API_KEY and API_SECRET):
        raise ValueError("APCA_API_KEY_ID / APCA_API_SECRET_KEY fehlen.")
    return tradeapi.REST(API_KEY, API_SECRET, API_BASE_URL, api_version="v2")

# ================================
# Market-Data-Client (alpaca-py)
# ================================
# 👉 Wir nutzen eine kleine Kompatibilitätsdatei (alpaca_data_compat.py),
#    damit 'MarketDataClient' so heißt wie in deiner App.
from alpaca_data_compat import MarketDataClient  # liefert StockHistoricalDataClient

@st.cache_resource(show_spinner=False)
def get_market_data_client() -> MarketDataClient:
    """
    Liefert den Historical Data Client (alpaca-py).
    Für IEX sind Key/Secret ebenfalls nötig.
    """
    if not (API_KEY and API_SECRET):
        raise ValueError("APCA_API_KEY_ID / APCA_API_SECRET_KEY fehlen.")
    return MarketDataClient(api_key=API_KEY, secret_key=API_SECRET)

def data_feed_label() -> str:
    return API_DATA_FEED.upper()

__all__ = [
    "API_KEY", "API_SECRET", "API_BASE_URL",
    "API_DATA_FEED", "SYMBOLS", "WATCHLIST",
    "TIMEFRAME", "FALLBACK_TIMEFRAME",
    "RSI_PERIOD", "RSI_LOWER", "RSI_UPPER",
    "MAX_TRADE_USD", "STOP_LOSS_PCT", "TAKE_PROFIT_PCT",
    "LOOP_SECONDS",
    "get_trading_api", "get_market_data_client", "data_feed_label",
]
