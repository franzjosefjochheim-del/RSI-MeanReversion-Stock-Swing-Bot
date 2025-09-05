import os
import logging
from dotenv import load_dotenv
from alpaca_trade_api.rest import TimeFrame

load_dotenv()

# --- API ---
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")
API_BASE_URL = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")

# --- Universum & Markt ---
WATCHLIST = [s.strip().upper() for s in os.getenv("WATCHLIST", "SPY,QQQ,AAPL,MSFT").split(",") if s.strip()]
TIMEFRAME = TimeFrame.Day           # Swing: Daily Bars
LOOP_SECONDS = 15 * 60              # alle 15 Minuten prüfen
TRADE_ONLY_WHEN_MARKET_OPEN = True  # nur wenn Markt offen

# --- RSI-Strategie ---
RSI_LEN = 2
BUY_RSI_MAX = 5        # Entry: RSI(2) <= 5
EXIT_RSI_MIN = 60      # Exit: RSI(2) >= 60
MAX_OPEN_POSITIONS = 5 # parallele Positionen begrenzen

# --- Risiko / Orders ---
MAX_TRADE_USD = 1000.0  # Notional pro Einstieg
STOP_LOSS_PCT = 0.03    # 3% SL
TAKE_PROFIT_PCT = 0.06  # 6% TP

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
