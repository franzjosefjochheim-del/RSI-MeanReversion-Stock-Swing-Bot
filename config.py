# config.py
# ---------------------------------------
# Alpaca-Client Wrapper für Trading + Data
# Kompatibel mit alpaca-py 0.20.x
# Enthält Kompatibilitäts-Methoden für alten Code (get_bars(...))
# ---------------------------------------

from __future__ import annotations

import os
import streamlit as st
import pandas as pd

# ---- Trading ----
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce

# ---- Market Data ----
try:
    from alpaca.data.historical.client import MarketDataClient as _DataClient  # alt
except Exception:
    from alpaca.data.historical.stock import StockHistoricalDataClient as _DataClient  # neu

from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# ================================
# API-Konfiguration
# ================================
API_KEY = os.getenv("APCA_API_KEY_ID", "")
API_SECRET = os.getenv("APCA_API_SECRET_KEY", "")
API_BASE_URL = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")

API_DATA_FEED: str = os.getenv("APCA_API_DATA_FEED", "iex").lower()
if API_DATA_FEED not in ("iex", "sip"):
    API_DATA_FEED = "iex"

# ================================
# Strategie-Parameter
# ================================
SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT"]
WATCHLIST = SYMBOLS

TIMEFRAME = "1Day"
FALLBACK_TIMEFRAME = "1Day"

RSI_PERIOD = 14
RSI_LOWER = 30
RSI_UPPER = 70

MAX_TRADE_USD = 2000.0
STOP_LOSS_PCT = 0.03
TAKE_PROFIT_PCT = 0.06

LOOP_SECONDS = 60 * 5


def _to_timeframe(tf_str: str) -> TimeFrame:
    s = (tf_str or "").lower()
    if s in ("1day", "1d", "day", "daily"):
        return TimeFrame.Day
    if s in ("1hour", "1h", "hour"):
        return TimeFrame.Hour
    return TimeFrame.Day


class RestCompat:
    """Wrapper für Alpaca-Py im Stil des alten alpaca_trade_api.REST."""

    def __init__(self, key: str, secret: str, base_url: str):
        self._is_paper = "paper" in (base_url or "").lower()
        self.trading = TradingClient(key, secret, paper=self._is_paper)
        self.data = _DataClient(key, secret)

    # --- Account / Positionen ---
    def get_account(self):
        return self.trading.get_account()

    def get_all_positions(self):
        return self.trading.get_all_positions()

    def close_position(self, symbol: str):
        return self.trading.close_position(symbol)

    # --- Orders ---
    def submit_order(self, symbol: str, qty: float, side: str = "buy"):
        from alpaca.trading.requests import MarketOrderRequest
        order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        return self.trading.submit_order(order_data=order)

    # --- Data (Mehrfachsymbole) ---
    def get_stock_bars(self, symbols: list[str], timeframe: str = "1Day", limit: int = 100):
        tf = _to_timeframe(timeframe)
        req = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=tf,
            limit=limit,
            feed=API_DATA_FEED,
        )
        return self.data.get_stock_bars(req)

    # --- Data (Einzelsymbol, Kompatibilitäts-Alias) ---
    def get_bars(self, symbol: str, timeframe: str = "1Day", limit: int = 100, **kwargs) -> pd.DataFrame:
        """
        Kompatibilität zur alten REST.get_bars(...).
        Zusätzliche kwargs (z. B. feed=...) werden ignoriert.
        """
        resp = self.get_stock_bars([symbol], timeframe=timeframe, limit=limit)

        bars_iter = []
        if hasattr(resp, "data") and isinstance(resp.data, dict):
            bars_iter = next(iter(resp.data.values()), [])
        elif hasattr(resp, "bars"):
            bars_iter = getattr(resp, "bars")
        else:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        rows = []
        for b in bars_iter or []:
            ts = getattr(b, "timestamp", None)
            rows.append(
                {
                    "timestamp": ts,
                    "open": float(getattr(b, "open", float("nan"))),
                    "high": float(getattr(b, "high", float("nan"))),
                    "low": float(getattr(b, "low", float("nan"))),
                    "close": float(getattr(b, "close", float("nan"))),
                    "volume": int(getattr(b, "volume", 0)),
                }
            )

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values("timestamp").reset_index(drop=True)
        return df


@st.cache_resource(show_spinner=False)
def get_api() -> RestCompat:
    if not (API_KEY and API_SECRET):
        raise ValueError("❌ Alpaca API Keys fehlen. Bitte APCA_API_KEY_ID und APCA_API_SECRET_KEY setzen.")
    return RestCompat(API_KEY, API_SECRET, API_BASE_URL)
