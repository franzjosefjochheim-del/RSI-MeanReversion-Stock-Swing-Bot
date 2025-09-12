#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RSI Mean-Reversion – Trading Engine (Paper)
- Läuft als --once (einmal handeln) oder --loop (Endlosschleife)
- Nutzt IMMER die letzte ABGESCHLOSSENE Kerze für TF=1Day
- Führt im Paper-Account Market-Orders aus:
    * BUY (Notional, z.B. 100 USD) wenn RSI <= 30 und keine Position vorhanden
    * SELL (alle Shares)          wenn RSI >= 70 und Position vorhanden
"""

import os
import time
import argparse
import datetime as dt
from typing import Optional, Dict, List

import pandas as pd
import numpy as np

# --- Alpaca: Marktdaten (neue API) ---
from alpaca.data.historical.client import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# --- Alpaca: Trading (Paper) ---
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, NotionalOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce


# =========================
#   KONFIGURATION (ENV)
# =========================
API_KEY = os.getenv("APCA_API_KEY_ID", "")
API_SECRET = os.getenv("APCA_API_SECRET_KEY", "")
API_BASE_URL = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")  # informativ
API_DATA_FEED = os.getenv("APCA_API_DATA_FEED", "iex").lower()  # "iex" (free) oder "sip"

# Handelsparameter
WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT"]
TIMEFRAME = "1Day"           # nur Daily vorgesehen
RSI_PERIOD = 14
RSI_LOW = 30.0               # Kauf-Schwelle
RSI_HIGH = 70.0              # Verkaufs-Schwelle

# Notional-Kaufsumme (USD) – pro BUY Order
TRADE_NOTIONAL_USD = float(os.getenv("TRADE_NOTIONAL_USD", "100"))

# Loop-Intervall (Sekunden)
LOOP_INTERVAL_SEC = 300


# =========================
#   HILFSFUNKTIONEN
# =========================
def _now_utc() -> dt.datetime:
    # Zeitzonen-sicher, ohne Deprecation-Warnung
    return dt.datetime.now(dt.timezone.utc)


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Einfacher RSI (auf Schlusskursen)."""
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    gain_sma = pd.Series(gain, index=series.index).rolling(period, min_periods=period).mean()
    loss_sma = pd.Series(loss, index=series.index).rolling(period, min_periods=period).mean()
    rs = gain_sma / loss_sma
    out = 100.0 - (100.0 / (1.0 + rs))
    return out


# ---------- Alpaca Clients ----------
def get_market_client() -> StockHistoricalDataClient:
    if not API_KEY or not API_SECRET:
        raise RuntimeError("API-Schlüssel fehlen (APCA_API_KEY_ID / APCA_API_SECRET_KEY).")
    return StockHistoricalDataClient(API_KEY, API_SECRET)


def get_trading_client() -> TradingClient:
    if not API_KEY or not API_SECRET:
        raise RuntimeError("API-Schlüssel fehlen (APCA_API_KEY_ID / APCA_API_SECRET_KEY).")
    # paper=True wählt automatisch den Paper-Endpunkt
    return TradingClient(API_KEY, API_SECRET, paper=True)


# ---------- Datenabruf ----------
def fetch_daily_bars(symbol: str, lookback_days: int = 400) -> pd.DataFrame:
    """
    Holt ausreichend viele Tageskerzen und liefert DataFrame mit Spalten ['t','o','h','l','c','v'].
    Wir nehmen später die letzte ABGESCHLOSSENE Kerze.
    """
    client = get_market_client()
    end = _now_utc()
    start = end - dt.timedelta(days=lookback_days)

    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        adjustment="raw",
        feed=API_DATA_FEED,
        limit=5000,
    )
    resp = client.get_stock_bars(req)

    if symbol not in resp.data or len(resp.data[symbol]) == 0:
        return pd.DataFrame()

    rows: List[Dict] = []
    for bar in resp.data[symbol]:
        rows.append({
            "t": pd.Timestamp(bar.timestamp).tz_convert("UTC"),
            "o": float(bar.open),
            "h": float(bar.high),
            "l": float(bar.low),
            "c": float(bar.close),
            "v": int(bar.volume or 0),
        })
    df = pd.DataFrame(rows).sort_values("t").reset_index(drop=True)
    return df


def last_completed_daily_row(df: pd.DataFrame) -> Optional[pd.Series]:
    """Gibt die letzte ABGESCHLOSSENE Tageszeile zurück (Datum < heute_UTC)."""
    if df.empty:
        return None
    today_utc = pd.Timestamp(_now_utc().date(), tz="UTC")
    completed = df[df["t"] < today_utc].copy()
    if completed.empty:
        # Fallback: notfalls vorletzte Zeile
        if len(df) >= 2:
            return df.iloc[-2]
        return None
    return completed.iloc[-1]


def compute_rsi_on_df(df: pd.DataFrame, period: int = RSI_PERIOD) -> Optional[float]:
    if df.empty or len(df) < period + 1:
        return None
    df = df.copy()
    df["rsi"] = rsi(df["c"], period=period)
    return float(df["rsi"].iloc[-1])


# ---------- Trading-Helper ----------
def get_position_qty(client: TradingClient, symbol: str) -> int:
    """Gibt aktuelle Positions-Stückzahl für symbol zurück (0 wenn keine)."""
    try:
        pos = client.get_open_position(symbol)
        return int(float(pos.qty))
    except Exception:
        return 0  # keine Position


def place_buy_notional(client: TradingClient, symbol: str, usd_amount: float):
    """Kauft Market für 'usd_amount' (Notional)."""
    order = NotionalOrderRequest(
        symbol=symbol,
        notional=usd_amount,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
    )
    return client.submit_order(order)


def place_sell_all(client: TradingClient, symbol: str, qty: int):
    """Verkauft Market alle vorhandenen Shares."""
    if qty <= 0:
        return None
    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    )
    return client.submit_order(order)


def decide_action(last_close: float, last_rsi: float) -> str:
    """Einfache Mean-Reversion-Heuristik."""
    if last_rsi is None or np.isnan(last_rsi):
        return "SKIP"
    if last_rsi <= RSI_LOW:
        return "BUY"
    if last_rsi >= RSI_HIGH:
        return "SELL"
    return "HOLD"


# =========================
#   HAUPT-LOGIK
# =========================
def trade_once() -> None:
    print(f"[BOT] Starte Runde • Feed={API_DATA_FEED} • TF={TIMEFRAME}")
    tclient = get_trading_client()

    for symbol in WATCHLIST:
        try:
            df = fetch_daily_bars(symbol)
            if df.empty:
                print(f"[BOT] {symbol}: Keine Bars – überspringe.")
                continue

            last_row = last_completed_daily_row(df)
            if last_row is None:
                print(f"[BOT] {symbol}: Keine abgeschlossene Tageskerze – überspringe.")
                continue

            last_rsi = compute_rsi_on_df(df)
            action = decide_action(last_row["c"], last_rsi)
            print(f"[BOT] {symbol}: Close={last_row['c']:.2f} • RSI={last_rsi} ⇒ {action}")

            # --- Orders ausführen (Paper) ---
            pos_qty = get_position_qty(tclient, symbol)

            if action == "BUY" and pos_qty == 0:
                try:
                    o = place_buy_notional(tclient, symbol, TRADE_NOTIONAL_USD)
                    print(f"[BOT] {symbol}: BUY Notional {TRADE_NOTIONAL_USD:.2f} USD → OrderID={o.id}")
                except Exception as oe:
                    print(f"[BOT] {symbol}: BUY-Fehler: {oe}")

            elif action == "SELL" and pos_qty > 0:
                try:
                    o = place_sell_all(tclient, symbol, pos_qty)
                    print(f"[BOT] {symbol}: SELL {pos_qty} Stk → OrderID={o.id}")
                except Exception as oe:
                    print(f"[BOT] {symbol}: SELL-Fehler: {oe}")

            else:
                # HOLD, SKIP oder Regel greift nicht (z.B. BUY aber es gibt schon Position)
                pass

        except Exception as e:
            print(f"[BOT] {symbol}: Fehler: {e}")

    print("[BOT] Runde fertig.")


def loop_forever(interval_sec: int = LOOP_INTERVAL_SEC):
    print(f"[BOT] Starte Endlosschleife (Intervall {interval_sec}s).")
    while True:
        trade_once()
        time.sleep(interval_sec)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true", help="Eine Runde ausführen und beenden.")
    p.add_argument("--loop", action="store_true", help="Endlosschleife.")
    args = p.parse_args()

    if args.once:
        trade_once()
        return
    if args.loop:
        loop_forever()
        return

    # Default: einmal ausführen
    trade_once()


if __name__ == "__main__":
    main()
