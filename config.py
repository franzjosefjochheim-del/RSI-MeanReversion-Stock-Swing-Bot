# config.py
# ---------------------------------------
# Zentrale Konfiguration + Alpaca-Client (nur alpaca-py)
# Kompatibel mit alpaca-py 0.20.x (neuer Datenclient-Pfad)
# und optional mit älteren Pfaden (Fallback-Import).
# ---------------------------------------

from __future__ import annotations

import os
import streamlit as st

# ---- Trading (Account/Orders) ----
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce

# ---- Market Data (Bars) ----
# In neueren Versionen (0.20.x) heißt der Client StockHistoricalDataClient
# und sitzt unter alpaca.data.historical.stock. Ältere Beispiele nutzten
# MarketDataClient unter alpaca.data.historical.client (nicht mehr vorhanden).
try:
    # älterer Pfad (falls in manchen Umgebungen noch vorhanden)
    from alpaca.data.historical.client import MarketDataClient as _DataClient  # type: ignore
except Exception:
    # aktueller Pfad (0.20.x)
    from alpaca.data.historical.stock import StockHistoricalDataClient as _DataClient  # type: ignore

from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# ================================
# API-Konfiguration (ENV Variablen)
# ================================
API_KEY = os.getenv("APCA_API_KEY_ID", "")
API_SECRET = os.getenv("APCA_API_SECRET_KEY", "")
API_BASE_URL = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")

# Datenfeed: standardmäßig "iex", erlaubt: iex | sip
API_DATA_FEED: str = os.getenv("APCA_API_DATA_FEED", "iex").lower()
if API_DATA_FEED not in ("iex", "sip"):
    API_DATA_FEED = "iex"

# ================================
# Strategie-Parameter
# ================================
SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT"]
WATCHLIST = SYMBOLS  # Alias für Rückwärtskompatibilität

# Standard-Zeitrahmen + Fallback
TIMEFRAME = "1Day"          # "1Day" | "1Hour"
FALLBACK_TIMEFRAME = "1Day"

# RSI
RSI_PERIOD = 14
RSI_LOWER = 30
RSI_UPPER = 70

# Risiko & Positionsgrößen
MAX_TRADE_USD = 2000.0
STOP_LOSS_PCT = 0.03
TAKE_PROFIT_PCT = 0.06

# Bot-Loop (nur falls ein Worker läuft)
LOOP_SECONDS = 60 * 5


# ===========================================
# Kompatibilitäts-Wrapper für alpaca-py → REST
# ===========================================
class RestCompat:
    """
    Schlanker Wrapper, der die wichtigsten Methoden der alten
    alpaca_trade_api.REST 'nachbildet' – mit alpaca-py unter der Haube.
    """

    def __init__(self, key: str, secret: str, base_url: str):
        self._is_paper = "paper" in (base_url or "").lower()
        # Trading-Client (Account/Positionen/Orders)
        self.trading = TradingClient(
            api_key=key,
            secret_key=secret,
            paper=self._is_paper,
        )
        # Market-Data-Client (historische Aktien-Bars)
        self.data = _DataClient(
            api_key=key,
            secret_key=secret,
        )

    # ---------- Account / Positionen ----------
    def get_account(self):
        return self.trading.get_account()

    def get_all_positions(self):
        return self.trading.get_all_positions()

    def close_position(self, symbol: str):
        return self.trading.close_position(symbol)

    # ---------- Orders (einfaches Beispiel) ----------
    def submit_order(self, symbol: str, qty: float, side: str = "buy"):
        from alpaca.trading.requests import MarketOrderRequest

        order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        return self.trading.submit_order(order_data=order)

    # ---------- Daten (Bars) ----------
    def get_stock_bars(self, symbols: list[str], timeframe: str = "1Day", limit: int = 100):
        tf = _to_timeframe(timeframe)
        req = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=tf,
            limit=limit,
            feed=API_DATA_FEED,
        )
        return self.data.get_stock_bars(req)


def _to_timeframe(tf_str: str) -> TimeFrame:
    s = (tf_str or "").lower()
    if s in ("1day", "1d", "day", "daily"):
        return TimeFrame.Day
    if s in ("1hour", "1h", "hour"):
        return TimeFrame.Hour
    return TimeFrame.Day


# ================================
# Gecachter API-Client
# ================================
@st.cache_resource(show_spinner=False)
def get_api() -> RestCompat:
    if not (API_KEY and API_SECRET):
        raise ValueError(
            "❌ Alpaca API Keys fehlen. Bitte APCA_API_KEY_ID und APCA_API_SECRET_KEY setzen."
        )
    return RestCompat(API_KEY, API_SECRET, API_BASE_URL)
