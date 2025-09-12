#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RSI Mean-Reversion – Trading Engine
- Läuft als --once (einmal handeln) oder --loop (Endlosschleife)
- Nutzt IMMER die letzte ABGESCHLOSSENE Kerze für TF=1Day
"""

import os
import sys
import time
import argparse
import datetime as dt
from typing import Optional, Dict, List

from alpaca.data.historical import StockHistoricalDataClient

from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import pandas as pd
import numpy as np

# --- Konfiguration aus ENV ---
API_KEY = os.getenv("APCA_API_KEY_ID", "")
API_SECRET = os.getenv("APCA_API_SECRET_KEY", "")
API_BASE_URL = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")
API_DATA_FEED = os.getenv("APCA_API_DATA_FEED", "iex").lower()  # iex oder sip

WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT"]
TIMEFRAME = "1Day"  # nur Daily vorgesehen
RSI_PERIOD = 14
RSI_LOW = 30.0
RSI_HIGH = 70.0
LOOP_INTERVAL_SEC = 300

def _now_utc() -> dt.datetime:
    return dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Einfacher RSI auf Schlusskursen."""
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    gain_sma = pd.Series(gain, index=series.index).rolling(period, min_periods=period).mean()
    loss_sma = pd.Series(loss, index=series.index).rolling(period, min_periods=period).mean()
    rs = gain_sma / loss_sma
    out = 100.0 - (100.0 / (1.0 + rs))
    return out

def get_market_client() -> StockHistoricalDataClient:
    if not API_KEY or not API_SECRET:
        raise RuntimeError("API-Schlüssel fehlen (APCA_API_KEY_ID / APCA_API_SECRET_KEY).")
    return StockHistoricalDataClient(API_KEY, API_SECRET)

def fetch_daily_bars(symbol: str, lookback_days: int = 400) -> pd.DataFrame:
    """Holt ausreichend viele Tageskerzen und liefert DataFrame mit Spalten ['t','o','h','l','c','v'].
    Wir nehmen später die letzte ABGESCHLOSSENE Kerze."""
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

    rows = []
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
    """Gibt die letzte ABGESCHLOSSENE Tageszeile zurück."""
    if df.empty:
        return None
    # Eine Tageskerze ist abgeschlossen, wenn ihr Datum < heute_UTC ist.
    today_utc = pd.Timestamp(_now_utc().date(), tz="UTC")
    completed = df[df["t"] < today_utc].copy()
    if completed.empty:
        # Fallback: manchmal ist die letzte Kerze schon „fertig“ obwohl t == today (je nach Anbieter).
        # Dann nehmen wir einfach die vorletzte Kerze.
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

def decide_action(last_close: float, last_rsi: float) -> str:
    """Einfache Mean-Reversion-Heuristik."""
    if last_rsi is None:
        return "SKIP"
    if last_rsi <= RSI_LOW:
        return "BUY"
    if last_rsi >= RSI_HIGH:
        return "SELL"
    return "HOLD"

def trade_once() -> None:
    print(f"[BOT] Starte Runde • Feed={API_DATA_FEED} • TF={TIMEFRAME}")
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
            if last_rsi is None or np.isnan(last_rsi):
                print(f"[BOT] {symbol}: Keine valide RSI-Berechnung – überspringe.")
                continue

            action = decide_action(last_row["c"], last_rsi)
            print(f"[BOT] {symbol}: Close={last_row['c']:.2f} • RSI={last_rsi:.1f} ⇒ {action}")

            # TODO: Hier Orders platzieren (über Trading-API) – aktuell nur Log.
            # Beispiel-Stub:
            # place_order(symbol, action, qty=... )

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
