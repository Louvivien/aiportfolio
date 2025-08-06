# backend/app/main.py

from datetime import datetime

from bson import ObjectId
from fastapi import FastAPI, HTTPException

from .calc import total_market_value, total_unrealized_pl
from .database import db
from .models import (PositionCreate, PositionModel, SummaryModel, TagCreate,
                     TagModel, TagSummaryModel)
from .price_service import get_current_price

app = FastAPI(title="AI Portfolio")

# ── Tag CRUD ───────────────────────────────────────────────────────────────────


@app.post("/tags", response_model=TagModel)
async def create_tag(tag: TagCreate):
    if await db.tags.find_one({"name": tag.name}):
        raise HTTPException(status_code=409, detail="Tag already exists")
    now = datetime.utcnow()
    doc = {"name": tag.name, "created_at": now, "updated_at": now}
    res = await db.tags.insert_one(doc)
    new = await db.tags.find_one({"_id": res.inserted_id})
    return TagModel(**new)


@app.get("/tags", response_model=list[TagModel])
async def read_tags():
    docs = await db.tags.find().to_list(1000)
    return [TagModel(**d) for d in docs]


@app.put("/tags/{tag_id}", response_model=TagModel)
async def update_tag(tag_id: str, tag: TagCreate):
    if not ObjectId.is_valid(tag_id):
        raise HTTPException(404, "Tag not found")
    now = datetime.utcnow()
    res = await db.tags.update_one(
        {"_id": ObjectId(tag_id)}, {"$set": {"name": tag.name, "updated_at": now}}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Tag not found")
    updated = await db.tags.find_one({"_id": ObjectId(tag_id)})
    return TagModel(**updated)


@app.delete("/tags/{tag_id}")
async def delete_tag(tag_id: str):
    if not ObjectId.is_valid(tag_id):
        raise HTTPException(404, "Tag not found")
    res = await db.tags.delete_one({"_id": ObjectId(tag_id)})
    if res.deleted_count == 0:
        raise HTTPException(404, "Tag not found")
    # remove the tag reference from all positions
    await db.positions.update_many({}, {"$pull": {"tags": ObjectId(tag_id)}})
    return {"message": "Tag deleted"}


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _get_tag_names(tag_ids: list[ObjectId]) -> list[str]:
    docs = await db.tags.find({"_id": {"$in": tag_ids}}).to_list(len(tag_ids))
    # map each ObjectId to its name
    name_map = {d["_id"]: d["name"] for d in docs}
    return [name_map.get(tid, "") for tid in tag_ids]


# ── Position CRUD with tag-name resolution ─────────────────────────────────────


@app.post("/positions", response_model=PositionModel)
async def create_position(position: PositionCreate):
    now = datetime.utcnow()
    # upsert tags and collect ObjectIds
    tag_ids = []
    for name in position.tags or []:
        tag = await db.tags.find_one({"name": name})
        if not tag:
            res = await db.tags.insert_one(
                {"name": name, "created_at": now, "updated_at": now}
            )
            tag_ids.append(res.inserted_id)
        else:
            tag_ids.append(tag["_id"])
    # build and insert
    doc = {
        "symbol": position.symbol,
        "quantity": position.quantity,
        "cost_price": position.cost_price,
        "tags": tag_ids,
        "created_at": now,
        "updated_at": now,
    }
    res = await db.positions.insert_one(doc)
    new = await db.positions.find_one({"_id": res.inserted_id})
    # enrich for response
    new["current_price"] = await get_current_price(new["symbol"])
    new["tags"] = await _get_tag_names(new["tags"])
    return PositionModel(**new)


@app.get("/positions", response_model=list[PositionModel])
async def read_positions():
    docs = await db.positions.find().to_list(1000)
    out = []
    for d in docs:
        d["current_price"] = await get_current_price(d["symbol"])
        d["tags"] = await _get_tag_names(d["tags"])
        out.append(PositionModel(**d))
    return out


@app.get("/positions/summary", response_model=SummaryModel)
async def get_positions_summary():
    """
    Compute and return total market value and total unrealized P/L
    across all positions.
    """
    # 1) Load & enrich all positions
    raw = await db.positions.find().to_list(1000)
    positions = []
    for d in raw:
        d["current_price"] = await get_current_price(d["symbol"])
        d["tags"] = await _get_tag_names(d["tags"])
        positions.append(PositionModel(**d))

    # 2) Compute totals
    total_mv = total_market_value(positions)
    total_pl = total_unrealized_pl(positions)

    return SummaryModel(total_market_value=total_mv, total_unrealized_pl=total_pl)


@app.get("/positions/tags/summary", response_model=list[TagSummaryModel])
async def get_tags_summary():
    """
    Return per-tag aggregates:
      - total_quantity
      - total_market_value
      - total_unrealized_pl
    """
    # 1) Fetch all raw positions
    raw = await db.positions.find().to_list(1000)

    # 2) Build a running summary per tag name
    summary: dict[str, dict] = {}
    for d in raw:
        # get live price (or 0.0 fallback)
        price = await get_current_price(d["symbol"])
        qty = d["quantity"]
        unreal_pl = qty * (price - d["cost_price"])
        # resolve tag ObjectIds → names
        tag_names = await _get_tag_names(d["tags"])
        for name in tag_names:
            if name not in summary:
                summary[name] = {
                    "total_quantity": 0.0,
                    "total_market_value": 0.0,
                    "total_unrealized_pl": 0.0,
                }
            summary[name]["total_quantity"] += qty
            summary[name]["total_market_value"] += qty * price
            summary[name]["total_unrealized_pl"] += unreal_pl

    # 3) Serialize to list of TagSummaryModel
    results = []
    for name, vals in summary.items():
        results.append(
            TagSummaryModel(
                tag=name,
                total_quantity=vals["total_quantity"],
                total_market_value=vals["total_market_value"],
                total_unrealized_pl=vals["total_unrealized_pl"],
            )
        )
    return results


@app.get("/positions/{position_id}", response_model=PositionModel)
async def read_position(position_id: str):
    if not ObjectId.is_valid(position_id):
        raise HTTPException(404, "Position not found")
    d = await db.positions.find_one({"_id": ObjectId(position_id)})
    if not d:
        raise HTTPException(404, "Position not found")
    d["current_price"] = await get_current_price(d["symbol"])
    d["tags"] = await _get_tag_names(d["tags"])
    return PositionModel(**d)


@app.put("/positions/{position_id}", response_model=PositionModel)
async def update_position(position_id: str, position: PositionCreate):
    if not ObjectId.is_valid(position_id):
        raise HTTPException(404, "Position not found")
    now = datetime.utcnow()
    tag_ids = []
    for name in position.tags or []:
        tag = await db.tags.find_one({"name": name})
        if not tag:
            res = await db.tags.insert_one(
                {"name": name, "created_at": now, "updated_at": now}
            )
            tag_ids.append(res.inserted_id)
        else:
            tag_ids.append(tag["_id"])
    update_data = {
        "symbol": position.symbol,
        "quantity": position.quantity,
        "cost_price": position.cost_price,
        "tags": tag_ids,
        "updated_at": now,
    }
    res = await db.positions.update_one(
        {"_id": ObjectId(position_id)}, {"$set": update_data}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Position not found")
    d = await db.positions.find_one({"_id": ObjectId(position_id)})
    d["current_price"] = await get_current_price(d["symbol"])
    d["tags"] = await _get_tag_names(d["tags"])
    return PositionModel(**d)


@app.delete("/positions/{position_id}")
async def delete_position(position_id: str):
    if not ObjectId.is_valid(position_id):
        raise HTTPException(404, "Position not found")
    res = await db.positions.delete_one({"_id": ObjectId(position_id)})
    if res.deleted_count == 0:
        raise HTTPException(404, "Position not found")
    return {"message": "Position deleted"}
