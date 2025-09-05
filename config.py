# config.py
import os
from dotenv import load_dotenv

# .env lokal laden (Render nutzt Environment Vars)
load_dotenv()

# ---------------------------------
# Alpaca API Credentials
# ---------------------------------
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")
API_BASE_URL = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")

# Datenfeed: "iex" (kostenlos) oder "sip" (kostenpflichtig)
API_DATA_FEED = os.getenv("APCA_API_DATA_FEED", "iex")

# ---------------------------------
# Strategie-Parameter RSI Mean Reversion
# ---------------------------------
WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT"]

TIMEFRAME = "1Day"   # Daily Bars
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

MAX_TRADE_USD = 2000.0   # Maximaler Einsatz pro Trade
STOP_LOSS_PCT = 0.03     # 3% Stop-Loss
TAKE_PROFIT_PCT = 0.06   # 6% Take-Profit

# ---------------------------------
# Bot-Loop
# ---------------------------------
LOOP_SECONDS = 60 * 15  # alle 15 Minuten prüfen
