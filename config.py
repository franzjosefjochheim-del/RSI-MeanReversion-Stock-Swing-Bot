# config.py
import os
import alpaca_trade_api as tradeapi

# -----------------------------------------------------
# Alpaca API Keys (werden von Render als Environment Variablen gesetzt)
# -----------------------------------------------------
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")
API_BASE_URL = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")

# Feed (iex = kostenlos, sip = kostenpflichtig)
API_DATA_FEED = os.getenv("APCA_API_DATA_FEED", "iex")

# -----------------------------------------------------
# Trading Parameter
# -----------------------------------------------------
SYMBOL = "AAPL"
WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT"]

TIMEFRAME = "1Hour"       # oder "1Day"
RSI_PERIOD = 14
RSI_LOWER = 30
RSI_UPPER = 70

MAX_TRADE_USD = 2000.0    # Maximaler Einsatz pro Trade
STOP_LOSS_PCT = 0.03      # 3% Stop Loss
TAKE_PROFIT_PCT = 0.06    # 6% Take Profit

# -----------------------------------------------------
# API Client Factory
# -----------------------------------------------------
def get_api():
    """Initialisiert den Alpaca REST-Client."""
    if not (API_KEY and API_SECRET and API_BASE_URL):
        raise ValueError("Fehlende API Keys oder Base URL. Bitte Environment Variablen prüfen.")
    return tradeapi.REST(
        key_id=API_KEY,
        secret_key=API_SECRET,
        base_url=API_BASE_URL
    )
