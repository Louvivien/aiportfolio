# backend/tests/test_calc.py

from datetime import datetime

from backend.app.calc import total_market_value, total_unrealized_pl, unrealized_pl
from backend.app.models import PositionModel


# Line before: imports
def test_unrealized_pl_single():
    assert unrealized_pl(2, 100.0, 110.0) == 20.0


# Line before: test_unrealized_pl_single
def test_total_market_and_pl():
    now = datetime.utcnow()
    # Create two PositionModel instances
    p1 = PositionModel(
        symbol="AAPL",
        quantity=2,
        cost_price=100.0,
        current_price=110.0,
        tags=[],
        created_at=now,
        updated_at=now,
    )
    p2 = PositionModel(
        symbol="MSFT",
        quantity=1,
        cost_price=50.0,
        current_price=60.0,
        tags=[],
        created_at=now,
        updated_at=now,
    )
    positions = [p1, p2]
    # Total market value = 2*110 + 1*60 = 280
    assert total_market_value(positions) == 280.0
    # Total unrealized P/L = 20 + 10 = 30
    assert total_unrealized_pl(positions) == 30.0


# Line after: end of file
