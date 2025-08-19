# backend/app/price_service.py

from typing import Dict, List, Optional

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


async def get_prices(symbols: List[str]) -> Dict[str, dict]:
    """
    Return a dict per symbol with:
      - current: float | None
      - prev_close: float | None
      - change: float | None     (current - prev_close)
      - change_pct: float | None (change / prev_close)
      - long_name: str | None
    """
    out: Dict[str, dict] = {}
    if not symbols:
        return out

    # yfinance batch wrapper
    tickers = yf.Tickers(" ".join(symbols))
    for raw in symbols:
        sym = raw.upper()
        try:
            t = tickers.tickers.get(sym) or yf.Ticker(sym)

            # Try fast_info first
            current: Optional[float] = None
            prev_close: Optional[float] = None
            long_name: Optional[str] = None

            try:
                fi = getattr(t, "fast_info", None) or {}
                current = float(fi.get("last_price")) if fi.get("last_price") is not None else None
                prev_close = (
                    float(fi.get("previous_close"))
                    if fi.get("previous_close") is not None
                    else None
                )
            except Exception:
                pass

            # Fallback via history if needed
            if prev_close is None:
                try:
                    hist = t.history(period="2d")["Close"]
                    if len(hist) >= 2:
                        prev_close = float(hist.iloc[-2])
                    elif len(hist) == 1:
                        prev_close = float(hist.iloc[-1])
                except Exception:
                    pass

            # Long name
            try:
                info = t.get_info()
                long_name = info.get("longName") or info.get("shortName")
            except Exception:
                long_name = None

            # If current still None, try last close
            if current is None:
                try:
                    hist = t.history(period="1d")["Close"]
                    if len(hist):
                        current = float(hist.iloc[-1])
                except Exception:
                    pass

            change = None
            change_pct = None
            if current is not None and prev_close not in (None, 0):
                change = current - prev_close
                change_pct = change / prev_close

            out[sym] = {
                "current": current,
                "prev_close": prev_close,
                "change": change,
                "change_pct": change_pct,
                "long_name": long_name,
            }
        except Exception:
            out[sym] = {
                "current": None,
                "prev_close": None,
                "change": None,
                "change_pct": None,
                "long_name": None,
            }

    return out
