# config.py
import os
import logging
from dotenv import load_dotenv
from alpaca_trade_api.rest import TimeFrame  # v2 SDK

# Lokal .env laden (Render nutzt Environment Variablen)
load_dotenv()

# -------------------------------------------------------
# Alpaca API
# -------------------------------------------------------
API_KEY      = os.getenv("APCA_API_KEY_ID", "").strip()
API_SECRET   = os.getenv("APCA_API_SECRET_KEY", "").strip()
API_BASE_URL = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets").strip()

# Marktdaten-Feed (Paper = iex)
DATA_FEED = os.getenv("APCA_API_DATA_FEED", "iex").strip()

# -------------------------------------------------------
# Strategie-Parameter (RSI Mean-Reversion – Aktien-Swing)
# -------------------------------------------------------
TIMEFRAME       = TimeFrame.Day
RSI_LEN         = int(os.getenv("RSI_LEN", "2"))
RSI_OVERSOLD    = float(os.getenv("RSI_OVERSOLD", "10"))
RSI_OVERBOUGHT  = float(os.getenv("RSI_OVERBOUGHT", "90"))

WATCHLIST_ENV = os.getenv("WATCHLIST", "SPY,QQQ,AAPL,MSFT")
WATCHLIST = [s.strip().upper() for s in WATCHLIST_ENV.split(",") if s.strip()]

# -------------------------------------------------------
# (Optional) Risiko-Parameter
# -------------------------------------------------------
MAX_TRADE_USD   = float(os.getenv("MAX_TRADE_USD", "2000"))
STOP_LOSS_PCT   = float(os.getenv("STOP_LOSS_PCT", "0.03"))
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "0.06"))

# -------------------------------------------------------
# Logging
# -------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
