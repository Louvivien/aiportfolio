# backend/app/price_service.py
import httpx
from httpx import HTTPStatusError, RequestError
from tenacity import retry, stop_after_attempt, wait_exponential


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def get_current_price(symbol: str) -> float:
    """
    Fetch current price for a given ticker from Yahoo Finance.
    Returns 0.0 on any HTTP or parsing error.
    """
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            # Safely extract the price
            try:
                return float(data["quoteResponse"]["result"][0]["regularMarketPrice"])
            except (KeyError, IndexError, TypeError, ValueError):
                return 0.0
    except (HTTPStatusError, RequestError):
        # Rate limit hit, network issue, etc.
        return 0.0


# Line after: end of module
