# backend/app/test_db.py

import asyncio

from .database import db
from .models import PositionModel


async def main():
    # Line before: defining the sample document
    doc = {"symbol": "AAPL", "quantity": 1.0, "cost_price": 150.0, "tags": ["sample"]}
    res = await db.positions.insert_one(doc)
    print("Inserted ID:", res.inserted_id)

    # Line before: fetching the raw document back
    data = await db.positions.find_one({"_id": res.inserted_id})
    # ← Inject a dummy current_price for the Pydantic model
    data["current_price"] = data["cost_price"]
    # Line after: now safe to build the PositionModel
    pos = PositionModel(**data)
    print("Model:", pos)

    await db.positions.delete_one({"_id": res.inserted_id})


if __name__ == "__main__":
    asyncio.run(main())
