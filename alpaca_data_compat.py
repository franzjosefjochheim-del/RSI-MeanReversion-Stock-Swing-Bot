# alpaca_data_compat.py
"""
Kompatibilitäts-Layer für alpaca-py:
Stellt 'MarketDataClient' bereit und mapped auf den aktuellen
StockHistoricalDataClient aus alpaca.data.historical.
"""

try:
    from alpaca.data.historical import StockHistoricalDataClient as MarketDataClient
except Exception as exc:
    raise ImportError(
        "Konnte StockHistoricalDataClient aus alpaca.data.historical nicht laden. "
        "Prüfe, ob 'alpaca-py' korrekt installiert ist."
    ) from exc
