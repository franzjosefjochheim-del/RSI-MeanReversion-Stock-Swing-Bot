# trading_engine.py
# ------------------------------------------------------------
# Autonomer RSI-Mean-Reversion-Bot für Alpaca (Paper-Account)
# - holt Bars (IEX, 1Day), berechnet RSI
# - kauft, wenn RSI < RSI_LOWER und keine Position vorhanden
# - verkauft, wenn RSI > RSI_UPPER und Position vorhanden
# - optional Bracket-Order (Stop-Loss/Take-Profit) beim Einstieg
# - kann einmalig (--once) oder in Schleife (--loop) laufen
# ------------------------------------------------------------

from __future__ import annotations
import os
import time
import math
import argparse
import traceback
from typing import List, Optional

import pandas as pd
import numpy as np

# === deine bestehende Konfiguration wird hier verwendet ===
import config

# Alpaca-py (Daten & Trading)
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame


# -------------- Utilities --------------

def log(msg: str) -> None:
    print(f"[BOT] {msg}", flush=True)


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI."""
    if len(close) < period + 1:
        return pd.Series(index=close.index, dtype=float)

    delta = close.diff()
    gain = delta.clip(lower=0.0).rolling(period).mean()
    loss = (-delta.clip(upper=0.0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def get_clients():
    """Erzeuge Market-Data- & Trading-Client."""
    api_key = config.API_KEY
    api_secret = config.API_SECRET

    # Daten (IEX – daily)
    data_client = StockHistoricalDataClient(api_key, api_secret)

    # Trading (Paper)
    trading_client = TradingClient(api_key, api_secret, paper=True)
    return data_client, trading_client


def fetch_last_close_and_rsi(
    data_client: StockHistoricalDataClient,
    symbol: str,
    limit: int = 200,
    timeframe: str = "1Day",
    rsi_period: int = None,
) -> tuple[Optional[float], Optional[float]]:
    """Holt Bars & berechnet RSI. Liefert (last_close, last_rsi)."""
    if rsi_period is None:
        rsi_period = config.RSI_PERIOD

    tf = TimeFrame.Day if timeframe.lower() in ("1day", "day", "1d") else TimeFrame.Hour

    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=tf,
        limit=limit,
        feed=config.API_DATA_FEED,  # "iex"
    )
    bars = data_client.get_stock_bars(req).df
    if bars is None or bars.empty:
        return None, None

    # Falls Multiindex (symbol, time)
    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs(symbol, level=0)

    closes = bars["close"].astype(float)
    rsi = compute_rsi(closes, period=rsi_period)
    last_close = float(closes.iloc[-1])
    last_rsi = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else None
    return last_close, last_rsi


def get_position_qty(trading_client: TradingClient, symbol: str) -> int:
    """Liefert Stückzahl offener Position; 0 wenn keine."""
    try:
        pos = trading_client.get_open_position(symbol)
        return int(float(pos.qty))
    except Exception:
        return 0


def submit_bracket_buy(
    trading_client: TradingClient,
    symbol: str,
    qty: int,
    entry_price: float,
) -> None:
    """Kauft per Market-Order inkl. Take-Profit / Stop-Loss (falls konfiguriert)."""
    tp_req = None
    sl_req = None

    if config.TAKE_PROFIT_PCT and config.TAKE_PROFIT_PCT > 0:
        tp_price = round(entry_price * (1 + float(config.TAKE_PROFIT_PCT)), 2)
        tp_req = TakeProfitRequest(limit_price=tp_price)

    if config.STOP_LOSS_PCT and config.STOP_LOSS_PCT > 0:
        sl_price = round(entry_price * (1 - float(config.STOP_LOSS_PCT)), 2)
        # optional: limit_price für Stop-Limit setzen; hier reiner Stop-Market
        sl_req = StopLossRequest(stop_price=sl_price)

    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        take_profit=tp_req,
        stop_loss=sl_req,
    )
    trading_client.submit_order(order)
    log(f"Order BUY {symbol} x{qty} (Bracket: TP={tp_req is not None}, SL={sl_req is not None}) gesendet.")


def submit_market_sell(trading_client: TradingClient, symbol: str, qty: int) -> None:
    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    )
    trading_client.submit_order(order)
    log(f"Order SELL {symbol} x{qty} gesendet.")


# -------------- Strategie-Logik --------------

def process_symbol(data_client, trading_client, symbol: str) -> None:
    """Führt die Regeln für EIN Symbol aus."""
    try:
        last_close, last_rsi = fetch_last_close_and_rsi(
            data_client,
            symbol,
            limit=200,
            timeframe=config.TIMEFRAME,
            rsi_period=config.RSI_PERIOD,
        )

        if last_close is None or last_rsi is None:
            log(f"{symbol}: Keine valide Bar/RSI – überspringe.")
            return

        pos_qty = get_position_qty(trading_client, symbol)
        log(f"{symbol}: Close={last_close:.2f}, RSI={last_rsi:.1f}, Position={pos_qty}")

        # EXIT-Regel: RSI > RSI_UPPER und Position vorhanden -> verkaufen
        if pos_qty > 0 and last_rsi >= config.RSI_UPPER:
            submit_market_sell(trading_client, symbol, pos_qty)
            return

        # ENTRY-Regel: RSI < RSI_LOWER und KEINE Position -> kaufen
        if pos_qty == 0 and last_rsi <= config.RSI_LOWER:
            # Positionsgröße
            raw_qty = config.MAX_TRADE_USD / last_close
            qty = int(math.floor(raw_qty))
            if qty <= 0:
                log(f"{symbol}: MAX_TRADE_USD zu klein für Kauf – überspringe.")
                return
            submit_bracket_buy(trading_client, symbol, qty, last_close)
            return

        log(f"{symbol}: Keine Aktion.")

    except Exception as e:
        log(f"{symbol}: FEHLER: {e}")
        traceback.print_exc()


def run_once() -> None:
    data_client, trading_client = get_clients()
    log(f"Starte Runde • Feed={config.API_DATA_FEED} • TF={config.TIMEFRAME}")
    for symbol in config.WATCHLIST:
        process_symbol(data_client, trading_client, symbol)
    log("Runde fertig.")


def run_loop(sleep_seconds: int) -> None:
    log(f"Starte Endlosschleife (Intervall {sleep_seconds}s).")
    while True:
        run_once()
        time.sleep(sleep_seconds)


# -------------- CLI --------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RSI Mean-Reversion Trading Engine")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--once", action="store_true", help="Nur eine Runde ausführen und beenden")
    g.add_argument("--loop", action="store_true", help="Endlosschleife mit Intervall (config.LOOP_SECONDS)")

    args = parser.parse_args()

    if args.once:
        run_once()
    else:
        run_loop(int(config.LOOP_SECONDS))
