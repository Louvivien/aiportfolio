# backend/app/calc.py

from typing import List

from .models import PositionModel


def unrealized_pl(quantity: float, cost_price: float, current_price: float) -> float:
    """
    Compute unrealized P/L for one position.
    """
    return quantity * (current_price - cost_price)


def total_market_value(positions: List[PositionModel]) -> float:
    """
    Sum of (quantity × current_price) across all positions.
    """
    return sum(p.quantity * p.current_price for p in positions)


def total_unrealized_pl(positions: List[PositionModel]) -> float:
    """
    Sum of unrealized P/L across all positions.
    """
    return sum(
        unrealized_pl(p.quantity, p.cost_price, p.current_price) for p in positions
    )
