# backend/tests/test_positions_crud.py

import pytest


# Line before: imports
@pytest.mark.anyio
async def test_crud_flow(async_client):
    # 1) CREATE a position
    create_resp = await async_client.post(
        "/positions",
        json={"symbol": "TEST", "quantity": 1, "cost_price": 100, "tags": ["x"]},
    )
    assert create_resp.status_code == 200
    pos = create_resp.json()
    pos_id = pos["_id"]
    assert pos["symbol"] == "TEST"

    # 2) READ all positions
    list_resp = await async_client.get("/positions")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert any(p["_id"] == pos_id for p in data)

    # 3) READ one position
    get_resp = await async_client.get(f"/positions/{pos_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["symbol"] == "TEST"

    # 4) UPDATE the position
    upd_resp = await async_client.put(
        f"/positions/{pos_id}",
        json={"symbol": "TEST", "quantity": 2, "cost_price": 150, "tags": ["y"]},
    )
    assert upd_resp.status_code == 200
    updated = upd_resp.json()
    assert updated["quantity"] == 2
    assert "y" in updated["tags"]

    # 5) DELETE the position
    del_resp = await async_client.delete(f"/positions/{pos_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["message"] == "Position deleted"


# Line after: end of file
