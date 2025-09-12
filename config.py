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
SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT"]
WATCHLIST = SYMBOLS

# IEX (Paper) liefert keine Intraday-Bars → 1Day
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
# Market-Data-Client (alpaca-py)
# ================================
from alpaca_data_compat import MarketDataClient  # -> StockHistoricalDataClient

@st.cache_resource(show_spinner=False)
def get_market_data_client() -> MarketDataClient:
    """
    Liefert den Historical Data Client (alpaca-py).
    Für IEX sind Key/Secret nötig.
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
    "get_market_data_client", "data_feed_label",
]
