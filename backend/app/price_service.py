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
      - change_pct: intraday percent change in percent units (e.g. 1.27)
      - long_name: security long name (best-effort)
      - currency: trading currency (e.g. 'EUR', 'USD')
      - price_10d: close price ~10 trading days ago (best-effort)
      - change_10d_pct: (current / price_10d - 1) * 100
    """
    out: Dict[str, Dict] = {}

    for raw in symbols:
        s = raw.upper()
        try:
            t = yf.Ticker(raw)

            # --- Fast/live ---
            fast = getattr(t, "fast_info", None) or {}
            current = _to_float(fast.get("last_price") or fast.get("lastPrice") or fast.get("last"))
            prev = _to_float(fast.get("previous_close") or fast.get("previousClose"))
            currency = fast.get("currency")

            # Fallbacks via .info
            info = getattr(t, "info", {}) or {}
            if current is None:
                current = _to_float(info.get("regularMarketPrice"))
            if prev is None:
                prev = _to_float(info.get("regularMarketPreviousClose"))
            if not currency:
                currency = info.get("currency")
            long_name = info.get("longName") or info.get("shortName")

            # Intraday deltas
            change = (current - prev) if (current is not None and prev is not None) else None
            change_pct = (
                ((change / prev) * 100.0)
                if (change is not None and prev not in (None, 0))
                else None
            )

            # --- 10 trading days ago close (best-effort) ---
            price_10d = None
            try:
                hist = t.history(period="30d", interval="1d")  # enough to cover 10 sessions
                closes = hist["Close"].dropna()
                # Use the close 10 trading sessions before the last available close
                # (e.g., -11 index if we consider last close as -1)
                if len(closes) >= 11:
                    price_10d = float(closes.iloc[-11])
                elif len(closes) >= 2:
                    # fallback: oldest available (short history)
                    price_10d = float(closes.iloc[0])
            except Exception:
                price_10d = None

            change_10d_pct = (
                ((current / price_10d) - 1.0) * 100.0
                if (current not in (None, 0) and price_10d not in (None, 0))
                else None
            )

            out[s] = {
                "current": current,
                "change": change,
                "change_pct": change_pct,
                "long_name": long_name,
                "currency": currency,
                "price_10d": price_10d,
                "change_10d_pct": change_10d_pct,
            }
        except Exception:
            out[s] = {
                "current": None,
                "change": None,
                "change_pct": None,
                "long_name": None,
                "currency": None,
                "price_10d": None,
                "change_10d_pct": None,
            }

    return out
