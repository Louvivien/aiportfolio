import pytest
from httpx import AsyncClient
from httpx._transports.asgi import ASGITransport

from backend.app.main import app
from frontend.app import load_positions, load_summary, load_tag_summary


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_full_flow(client):
    # Create
    resp = await client.post(
        "/positions",
        json={"symbol": "INTG", "quantity": 2, "cost_price": 50, "tags": ["a", "b"]},
    )
    assert resp.status_code == 200
    pos = resp.json()
    pid = pos["_id"]

    # Read via API
    all_api = await client.get("/positions")
    assert any(p["_id"] == pid for p in all_api.json())

    # Read via front-end helper
    fe_positions = load_positions()
    assert any(p["_id"] == pid for p in fe_positions)

    # Update
    upd = await client.put(
        f"/positions/{pid}",
        json={"symbol": "INTG", "quantity": 5, "cost_price": 40, "tags": ["a"]},
    )
    assert upd.status_code == 200
    assert upd.json()["quantity"] == 5

    # Summaries via front-end helpers
    summ = load_summary()
    assert summ["total_market_value"] >= 0
    tag_summ = load_tag_summary()
    assert any(t["tag"] == "a" for t in tag_summ)

    # Delete
    d = await client.delete(f"/positions/{pid}")
    assert d.status_code == 200

    # Gone
    all_again = await client.get("/positions")
    assert not any(p["_id"] == pid for p in all_again.json())
