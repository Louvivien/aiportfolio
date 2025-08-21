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


def _to_float(x) -> Optional[float]:
    try:
        return float(x)
    except Exception:
        return None


async def get_prices(symbols: List[str]) -> Dict[str, Dict]:
    """
    Return a dict keyed by uppercased symbol with:
      - current: last traded price
      - change:  absolute intraday change (current - previous_close)
      - change_pct: intraday percent change **in percent units** (e.g. 1.27 for +1.27%)
      - long_name: security long name (best-effort)
    """
    out: Dict[str, Dict] = {}

    for raw in symbols:
        s = raw.upper()
        try:
            t = yf.Ticker(raw)

            # Prefer fast_info when available (fewer API calls)
            fast = getattr(t, "fast_info", None) or {}
            current = _to_float(fast.get("last_price") or fast.get("lastPrice") or fast.get("last"))
            prev = _to_float(fast.get("previous_close") or fast.get("previousClose"))

            # Fallback to .info if fast_info is missing anything
            if current is None or prev is None:
                info = t.info or {}
                current = current or _to_float(info.get("regularMarketPrice"))
                prev = prev or _to_float(info.get("regularMarketPreviousClose"))

            change = (current - prev) if (current is not None and prev is not None) else None
            change_pct = (
                (change / prev * 100.0) if (change is not None and prev not in (None, 0)) else None
            )

            # Long name best-effort
            info = getattr(t, "info", {}) or {}
            long_name = info.get("longName") or info.get("shortName")

            # NEW: currency (fast_info first, then info)
            currency = (fast.get("currency") if isinstance(fast, dict) else None) or info.get(
                "currency"
            )

            out[s] = {
                "current": current,
                "change": change,
                "change_pct": change_pct,  # <- now a real percent (1.27, not 0.0127)
                "long_name": long_name,
                "currency": currency,  # <-- NEW
            }
        except Exception:
            out[s] = {"current": None, "change": None, "change_pct": None, "long_name": None}

    return out
