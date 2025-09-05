import time
import logging
import traceback
import pandas as pd
import alpaca_trade_api as tradeapi

import config
import control
import strategy
import risk

log = logging.getLogger("rsi-bot")

def get_api():
    return tradeapi.REST(
        key_id=config.API_KEY,
        secret_key=config.API_SECRET,
        base_url=config.API_BASE_URL
    )

def get_bars(api, symbols, limit: int):
    """Stock-Bars holen; Ergebnis: dict[symbol] -> DataFrame mit 'close' etc."""
    out = {}
    try:
        df = api.get_bars(symbols, config.TIMEFRAME, limit=limit).df  # MultiIndex: (symbol, timestamp)
    except Exception as e:
        log.error("get_bars-Fehler: %s", e)
        return out

    if isinstance(df.index, pd.MultiIndex):
        for sym in symbols:
            if (sym,) in df.index.levels[0]:
                try:
                    sdf = df.loc[(sym,), :]
                    for c in ("open","high","low","close","volume","vwap"):
                        if c in sdf.columns:
                            sdf[c] = pd.to_numeric(sdf[c], errors="coerce")
                    out[sym] = sdf.dropna(subset=["close"])
                except Exception:
                    pass
    else:
        # falls Single-Index zurück kommt (einzelnes Symbol)
        for c in ("open","high","low","close","volume","vwap"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        out[symbols[0]] = df.dropna(subset=["close"])

    return out

def market_open(api) -> bool:
    if not config.TRADE_ONLY_WHEN_MARKET_OPEN:
        return True
    try:
        return bool(api.get_clock().is_open)
    except Exception:
        return True  # im Zweifel handeln (Paper)

def run():
    api = get_api()
    log.info("RSI Mean-Reversion Bot gestartet. Watchlist: %s", ",".join(config.WATCHLIST))

    while True:
        try:
            if control.is_paused():
                log.info("PAUSED – kein Trading in diesem Zyklus.")
                time.sleep(config.LOOP_SECONDS)
                continue

            if not market_open(api):
                log.info("Markt geschlossen – warte.")
                time.sleep(config.LOOP_SECONDS)
                continue

            # Daten holen
            bars_map = get_bars(api, config.WATCHLIST, limit=max(50, config.RSI_LEN+5))
            if not bars_map:
                log.warning("Keine Bars empfangen.")
                time.sleep(config.LOOP_SECONDS)
                continue

            # Offene Positionen
            try:
                all_pos = {p.symbol: p for p in api.list_positions()}
            except Exception:
                all_pos = {}
            open_count = len(all_pos)

            # Pro Symbol prüfen
            for sym, df in bars_map.items():
                if df is None or df.empty:
                    continue

                # Letzter Kurs
                last_price = float(df["close"].iloc[-1])
                has_pos = sym in all_pos
                entry_price = float(all_pos[sym].avg_entry_price) if has_pos else 0.0

                # RSI Signal
                sig = strategy.generate_signal_from_df(df)

                # Exit: SELL oder SL/TP
                if has_pos and (sig == "SELL" or risk.hit_stop_or_takeprofit(entry_price, last_price)):
                    api.submit_order(symbol=sym, side="sell", type="market",
                                     qty=all_pos[sym].qty, time_in_force="day")
                    log.info("SELL %s qty=%s @ ~%.2f (Signal/SL/TP)", sym, all_pos[sym].qty, last_price)
                    open_count = max(0, open_count - 1)
                    continue

                # Entry
                if sig == "BUY" and risk.should_enter(has_pos, open_count):
                    # Notional statt qty (einfacher für Aktien)
                    notional = min(float(api.get_account().cash) * 0.95, config.MAX_TRADE_USD)
                    if notional > 10:
                        api.submit_order(symbol=sym, side="buy", type="market",
                                         notional=str(round(notional, 2)), time_in_force="day")
                        log.info("BUY %s notional=$%.2f @ ~%.2f", sym, notional, last_price)
                        open_count += 1

        except Exception as e:
            log.error("Fehler: %s\n%s", e, traceback.format_exc())

        time.sleep(config.LOOP_SECONDS)

if __name__ == "__main__":
    run()
