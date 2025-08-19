# backend/app/price_service.py

from typing import Dict, List

import yfinance as yf


async def get_long_names(symbols: list[str]) -> dict[str, str | None]:
    """
    Return a map SYMBOL -> long_name (or None if unknown).
    We keep it resilient and tolerate failures per symbol.
    """
    out: dict[str, str | None] = {}
    for s in symbols:
        sym = s.upper()
        try:
            t = yf.Ticker(sym)
            info = t.info  # yfinance may hit network here
            out[sym] = info.get("longName") or info.get("shortName")
        except Exception:
            out[sym] = None
    return out


async def get_prices(symbols: List[str]) -> Dict[str, float]:
    """
    Fetch current prices for a list of ticker symbols using yfinance.
    Returns a dict {symbol: price or 0.0 if not found}.
    """
    prices: Dict[str, float] = {}

    if not symbols:
        return prices

    try:
        tickers = yf.Tickers(" ".join(symbols))  # batch call
        for sym in symbols:
            info = tickers.tickers.get(sym)
            if not info:
                prices[sym] = 0.0
                continue
            try:
                price = info.history(period="1d")["Close"].iloc[-1]
                prices[sym] = float(price)
            except Exception:
                prices[sym] = 0.0
    except Exception:
        # fail safe
        for sym in symbols:
            prices[sym] = 0.0

    return prices
