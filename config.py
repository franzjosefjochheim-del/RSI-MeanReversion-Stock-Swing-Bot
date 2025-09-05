# config.py
# Einstellungen für den RSI Mean-Reversion Bot (Dashboard)

import os
import logging
from dotenv import load_dotenv

# ---------------------------------------------------
# .env / Render-Environment einlesen
# ---------------------------------------------------
load_dotenv()

# Alpaca API – Keys & Endpunkte
# (Auf Render unter Environment Variables setzen)
API_KEY: str = os.getenv("APCA_API_KEY_ID", "")
API_SECRET: str = os.getenv("APCA_API_SECRET_KEY", "")

# Paper-Konto als Default (kann via ENV überschrieben werden)
API_BASE_URL: str = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")

# Datenfeed: automatisch auf "iex" zurückfallen, falls nicht gesetzt
API_DATA_FEED: str = os.getenv("APCA_API_DATA_FEED", "iex").lower()

# ---------------------------------------------------
# Strategie-Parameter (RSI Mean-Reversion)
# ---------------------------------------------------
# Watchlist (US-Aktien/ETFs)
WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT"]

# Zeitrahmen für die Signale (Alpaca v2 akzeptiert "1Hour", "1Day", ...)
TIMEFRAME = "1Hour"

# RSI-Schwellen
RSI_LOWER = 30    # Oversold → potentielles BUY
RSI_UPPER = 70    # Overbought → potentielles SELL

# Konservative Risiko-Defaults (für späteres Auto-Trading nützlich;
# im reinen Dashboard nicht zwingend verwendet)
MAX_TRADE_USD = 2000.0   # maximaler Einsatz je Trade
STOP_LOSS_PCT = 0.03     # 3% Stop Loss
TAKE_PROFIT_PCT = 0.06   # 6% Take Profit

# ---------------------------------------------------
# Logging
# ---------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Praktische Zusammenfassung, die wir im Footer anzeigen können
SUMMARY = {
    "watchlist": WATCHLIST,
    "timeframe": TIMEFRAME,
    "feed": API_DATA_FEED,
}
