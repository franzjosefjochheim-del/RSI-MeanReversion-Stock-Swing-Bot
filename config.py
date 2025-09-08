# config.py
import os
from dataclasses import dataclass
from typing import List

import streamlit as st
from alpaca.trading.client import TradingClient
from alpaca.data.historical.client import MarketDataClient
from alpaca.data.timeframe import TimeFrame as DataTimeFrame
from alpaca.data.enums import DataFeed


# ================================
# ENV / Grundeinstellungen
# ================================
API_KEY: str = os.getenv("APCA_API_KEY_ID", "")
API_SECRET: str = os.getenv("APCA_API_SECRET_KEY", "")
# WICHTIG: ohne /v2!
API_BASE_URL: str = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")

# Datenfeed: "iex" (Paper, delayed) oder "sip" (kostenpfl. Live)
RAW_FEED = (os.getenv("APCA_API_DATA_FEED", "iex") or "iex").lower()
DATA_FEED = DataFeed.IEX if RAW_FEED != "sip" else DataFeed.SIP

# ================================
# Strategie-Parameter
# ================================
SYMBOLS: List[str] = ["SPY", "QQQ", "AAPL", "MSFT"]
# Alias für UI
WATCHLIST = SYMBOLS

# IEX liefert für Paper verlässlich Daily-Bars.
DEFAULT_TIMEFRAME = "1Day"          # UI-Default
RSI_PERIOD = 14
RSI_LOWER = 30
RSI_UPPER = 70

MAX_TRADE_USD = 2000.0
STOP_LOSS_PCT = 0.03
TAKE_PROFIT_PCT = 0.06

# ================================
# Clients (Trading + Market Data)
# ================================
@st.cache_resource(show_spinner=False)
def get_trading_client() -> TradingClient:
    if not (API_KEY and API_SECRET and API_BASE_URL):
        raise ValueError("APCA_API_KEY_ID / APCA_API_SECRET_KEY / APCA_API_BASE_URL fehlen.")
    # paper=True erzwingt Paper-Endpoint Verhalten (wichtig bei Custom-Base-URL)
    return TradingClient(API_KEY, API_SECRET, paper=True)


@st.cache_resource(show_spinner=False)
def get_market_client() -> MarketDataClient:
    # Market Data hat eigenen Host, Keys sind die gleichen.
    return MarketDataClient(API_KEY, API_SECRET)


# Mapping für UI → alpaca.data.timeframe
TF_MAP = {
    "1Day": DataTimeFrame.Day,
    "1Hour": DataTimeFrame.Hour,  # bleibt im Code für spätere Erweiterung
}


@dataclass(frozen=True)
class AppConfig:
    symbols: List[str]
    rsi_period: int
    rsi_lower: int
    rsi_upper: int
    default_timeframe: str
    data_feed: DataFeed


APP = AppConfig(
    symbols=SYMBOLS,
    rsi_period=RSI_PERIOD,
    rsi_lower=RSI_LOWER,
    rsi_upper=RSI_UPPER,
    default_timeframe=DEFAULT_TIMEFRAME,
    data_feed=DATA_FEED,
)
