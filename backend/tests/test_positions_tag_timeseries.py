import pytest
from unittest.mock import patch


@pytest.mark.anyio
async def test_positions_tags_timeseries(async_client):
    from backend.app import main
    from backend.app.database import db

    async def fake_get_price_history(symbols, *, period="6mo", interval="1d"):
        assert sorted(symbols) == ["AAA", "BBB", "CCC", "EEE"]
        return {
            "AAA": [
                {"date": "2024-01-01", "close": 9.0},
                {"date": "2024-01-02", "close": 10.0},
            ],
            "BBB": [
                {"date": "2024-01-01", "close": 21.0},
                {"date": "2024-01-02", "close": 19.0},
            ],
            "CCC": [
                {"date": "2024-01-01", "close": 100.0},
                {"date": "2024-01-02", "close": 110.0},
            ],
            "EEE": [
                {"date": "2024-01-01", "close": 12.0},
                {"date": "2024-01-02", "close": 10.0},
            ],
        }

    growth_id = "tag_growth"
    income_id = "tag_income"
    await db.tags.insert_one({"_id": growth_id, "name": "Growth"})
    await db.tags.insert_one({"_id": income_id, "name": "Income"})

    await db.positions.insert_one(
        {
            "symbol": "AAA",
            "quantity": 10,
            "cost_price": 8.0,
            "tags": [growth_id],
            "is_closed": False,
        }
    )
    await db.positions.insert_one(
        {
            "symbol": "BBB",
            "quantity": 5,
            "cost_price": 20.0,
            "tags": [growth_id, income_id],
            "is_closed": False,
        }
    )
    await db.positions.insert_one(
        {
            "symbol": "CCC",
            "quantity": 1,
            "cost_price": 100.0,
            "tags": [income_id],
            "is_closed": False,
        }
    )
    await db.positions.insert_one(
        {
            "symbol": "EEE",
            "quantity": 2,
            "cost_price": 10.0,
            "tags": [],
            "is_closed": False,
        }
    )
    await db.positions.insert_one(
        {
            "symbol": "DDD",
            "quantity": 100,
            "cost_price": 1.0,
            "tags": [growth_id],
            "is_closed": True,  # closed positions should be ignored
        }
    )

    with patch.object(main, "get_price_history", fake_get_price_history):
        resp = await async_client.get("/positions/tags/timeseries?period=1mo&interval=1d")
    assert resp.status_code == 200
    data = resp.json()

    assert set(data["tags"].keys()) == {"Growth", "Income"}

    growth = data["tags"]["Growth"]
    assert len(growth) == 2
    assert growth[0]["date"] == "2024-01-01"
    assert growth[0]["market_value"] == pytest.approx(195.0)
    assert growth[0]["unrealized_pl"] == pytest.approx(15.0)
    assert growth[1]["date"] == "2024-01-02"
    assert growth[1]["market_value"] == pytest.approx(195.0)
    assert growth[1]["unrealized_pl"] == pytest.approx(15.0)

    income = data["tags"]["Income"]
    assert len(income) == 2
    assert income[0]["market_value"] == pytest.approx(205.0)
    assert income[0]["unrealized_pl"] == pytest.approx(5.0)
    assert income[1]["market_value"] == pytest.approx(205.0)
    assert income[1]["unrealized_pl"] == pytest.approx(5.0)

    total = data["total"]
    assert len(total) == 2
    assert total[0]["market_value"] == pytest.approx(319.0)
    assert total[0]["unrealized_pl"] == pytest.approx(19.0)
    assert total[1]["market_value"] == pytest.approx(325.0)
    assert total[1]["unrealized_pl"] == pytest.approx(25.0)


@pytest.mark.anyio
async def test_positions_tags_timeseries_empty(async_client):
    from backend.app import main

    async def fake_get_price_history(symbols, *, period="6mo", interval="1d"):
        # Should not be called when there are no open positions, but be lenient.
        return {}

    with patch.object(main, "get_price_history", fake_get_price_history):
        resp = await async_client.get("/positions/tags/timeseries")
    assert resp.status_code == 200
    assert resp.json() == {"tags": {}, "total": []}
