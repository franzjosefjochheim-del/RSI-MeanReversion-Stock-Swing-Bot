# config.py
# ---------------------------------------
# Zentrale Konfiguration + Alpaca-Client
# (nur alpaca-py, KEIN alpaca_trade_api)
# ---------------------------------------

from __future__ import annotations

import os
import streamlit as st

# alpaca-py (v0.20.0)
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
try:
    # alpaca-py <= 0.20
    from alpaca.data.historical.client import MarketDataClient  # type: ignore
except (ModuleNotFoundError, ImportError):  # pragma: no cover - fallback for newer SDK
    try:
        # alpaca-py >= 1.0 (module structure changed)
        from alpaca.data.historical.stock import (
            StockHistoricalDataClient as MarketDataClient,
        )
    except (ModuleNotFoundError, ImportError):
        # Some releases expose the class at top-level ``alpaca.data``
        from alpaca.data import StockHistoricalDataClient as MarketDataClient
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
# Watchlist / Symbole
SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT"]
# Alias für Rückwärtskompatibilität
WATCHLIST = SYMBOLS

# Standard-Zeitrahmen + Fallback (wenn 1h nicht verfügbar)
TIMEFRAME = "1Day"        # "1Day" | "1Hour"
FALLBACK_TIMEFRAME = "1Day"

# RSI-Einstellungen
RSI_PERIOD = 14
RSI_LOWER = 30
RSI_UPPER = 70

# Risiko & Positionsgrößen
MAX_TRADE_USD = 2000.0
STOP_LOSS_PCT = 0.03
TAKE_PROFIT_PCT = 0.06

# Bot-Loop (nur falls Worker separat läuft)
LOOP_SECONDS = 60 * 5

# ===========================================
# Kompatibilitäts-Wrapper für alpaca-py → REST
# damit bestehender Code weiter funktioniert
# ===========================================
class RestCompat:
    """
    Schlanker Wrapper, der die wichtigsten Methoden der alten
    alpaca_trade_api.REST 'nachbildet' – mit alpaca-py unter der Haube.
    """

    def __init__(self, key: str, secret: str, base_url: str):
        self._is_paper = "paper" in (base_url or "").lower()
        # Trading (Account, Positionen, Orders)
        self.trading = TradingClient(
            api_key=key,
            secret_key=secret,
            paper=self._is_paper,
        )
        # Marktdaten (Bars, Quotes …)
        self.data = MarketDataClient(
            api_key=key,
            secret_key=secret,
        )

    # ---------- Account / Positionen ----------
    def get_account(self):
        return self.trading.get_account()

    def get_all_positions(self):
        # Liefert Liste von Position-Objekten (wie früher)
        return self.trading.get_all_positions()

    def close_position(self, symbol: str):
        # Schließt die gesamte Position für ein Symbol
        return self.trading.close_position(symbol)

    # ---------- Orders (nur falls benötigt) ----------
    def submit_order(self, symbol: str, qty: float, side: str = "buy"):
        """
        Sehr einfache Market-Order. Nur verwenden, wenn dein Code das braucht.
        """
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
        """
        Liefert Bars für mehrere Symbole.
        Beispiel für Nutzung in deinem Code:
            req = api.get_stock_bars(["SPY"], "1Day", 200)
        """
        tf = _to_timeframe(timeframe)
        req = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=tf,
            limit=limit,
            feed=API_DATA_FEED,
        )
        return self.data.get_stock_bars(req)


# Hilfsfunktion: String → alpaca-py TimeFrame
def _to_timeframe(tf_str: str) -> TimeFrame:
    s = (tf_str or "").lower()
    if s in ("1day", "1d", "day", "daily"):
        return TimeFrame.Day
    if s in ("1hour", "1h", "hour"):
        return TimeFrame.Hour
    # Fallback
    return TimeFrame.Day


# ================================
# Bereitstellen eines (gecachten) Clients
# ================================
@st.cache_resource(show_spinner=False)
def get_api() -> RestCompat:
    if not (API_KEY and API_SECRET):
        raise ValueError(
            "❌ Alpaca API Keys fehlen. Bitte APCA_API_KEY_ID und APCA_API_SECRET_KEY setzen."
        )
    # API_BASE_URL wird derzeit nur genutzt, um paper/live zu erkennen.
    return RestCompat(API_KEY, API_SECRET, API_BASE_URL)
