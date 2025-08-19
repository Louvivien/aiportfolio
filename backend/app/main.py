from __future__ import annotations

"""
FastAPI app for the portfolio backend.

Endpoints:
- GET  /tags
- GET  /positions
- POST /positions
- PUT  /positions/{position_id}
- GET  /positions/summary
- GET  /positions/tags/summary
"""

from datetime import datetime
from typing import Any, Dict, List, Union

from bson import ObjectId
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .database import db
from .models import PositionCreate, PositionModel, PositionUpdate, TagModel
from .price_service import get_long_names, get_prices  # yfinance-backed

app = FastAPI(title="Portfolio Backend")

# CORS: allow local Streamlit (adjust for prod as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
def _oid(s: Union[str, ObjectId]) -> Union[ObjectId, str]:
    """Coerce a string to ObjectId if valid; otherwise return as-is."""
    if isinstance(s, ObjectId):
        return s
    return ObjectId(s) if ObjectId.is_valid(s) else s


def _stringify_id(d: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Return a shallow copy with _id as str (if present)."""
    if d is None:
        return None
    out: Dict[str, Any] = dict(d)
    if "_id" in out and isinstance(out["_id"], ObjectId):
        out["_id"] = str(out["_id"])
    return out


async def _get_tag_names(tag_ids: List[ObjectId]) -> List[str]:
    """Resolve a list of Tag ObjectIds to their names (missing → skip)."""
    if not tag_ids:
        return []
    docs = await db.tags.find({"_id": {"$in": tag_ids}}).to_list(len(tag_ids))
    name_by_id = {d["_id"]: d["name"] for d in docs}
    return [name_by_id.get(tid, "") for tid in tag_ids if tid in name_by_id]


async def _upsert_tags_return_ids(names: List[str]) -> List[ObjectId]:
    """Ensure each tag name exists; return list of tag ObjectIds (order preserved)."""
    out: List[ObjectId] = []
    now = datetime.utcnow()
    for name in names or []:
        doc = await db.tags.find_one({"name": name})
        if doc:
            out.append(doc["_id"])
        else:
            res = await db.tags.insert_one({"name": name, "created_at": now, "updated_at": now})
            out.append(res.inserted_id)
    return out


# ──────────────────────────────────────────────────────────────
# Tags
# ──────────────────────────────────────────────────────────────
@app.get("/tags", response_model=List[TagModel])
async def read_tags() -> List[TagModel]:
    """Return all tags (id + name)."""
    docs = await db.tags.find().to_list(None)
    return [TagModel(id=str(d["_id"]), name=d["name"]) for d in docs]


# ──────────────────────────────────────────────────────────────
# Positions
# ──────────────────────────────────────────────────────────────
@app.get("/positions", response_model=List[PositionModel])
async def read_positions() -> List[PositionModel]:
    """
    Return all positions enriched with:
      - current_price (closing price if closed, else live)
      - long_name (yfinance long/short name)
      - tag names (not IDs)
    """
    docs = await db.positions.find().to_list(1000)
    symbols = sorted({d["symbol"].upper() for d in docs})

    # Fetch live prices
    try:
        price_map = await get_prices(symbols)
    except Exception:
        price_map = {s: None for s in symbols}

    # Fetch long names
    try:
        names_map = await get_long_names(symbols)
    except Exception:
        names_map = {s: None for s in symbols}

    out: List[PositionModel] = []
    for d in docs:
        sym = d["symbol"].upper()
        live = price_map.get(sym)
        is_closed = bool(d.get("is_closed", False))
        closing_price = d.get("closing_price")
        # Prefer closing price when closed
        effective = closing_price if (is_closed and closing_price is not None) else live
        d["current_price"] = float(effective or 0.0)

        # Tags → names
        d["tags"] = await _get_tag_names(d.get("tags", []))

        # Attach long_name
        d["long_name"] = names_map.get(sym)

        # Convert _id to string for Pydantic model
        d = _stringify_id(d) or {}
        out.append(PositionModel(**d))

    return out


@app.post("/positions", response_model=PositionModel)
async def create_position(position: PositionCreate) -> PositionModel:
    """Create a position and return it enriched (same as GET /positions)."""
    now = datetime.utcnow()
    tag_ids = await _upsert_tags_return_ids(position.tags or [])
    doc: Dict[str, Any] = {
        "symbol": position.symbol.upper(),
        "quantity": position.quantity,
        "cost_price": position.cost_price,
        "tags": tag_ids,
        "is_closed": position.is_closed,
        "closing_price": position.closing_price,
        "created_at": now,
        "updated_at": now,
    }
    res = await db.positions.insert_one(doc)
    new = await db.positions.find_one({"_id": res.inserted_id})
    assert new is not None

    # Enrich price with the same rule as GET:
    try:
        price_map = await get_prices([new["symbol"].upper()])
    except Exception:
        price_map = {new["symbol"].upper(): 0.0}
    live = price_map.get(new["symbol"].upper())
    is_closed = bool(new.get("is_closed", False))
    closing_price = new.get("closing_price")
    effective = closing_price if (is_closed and closing_price is not None) else live
    new["current_price"] = float(effective or 0.0)

    # Long name
    try:
        names_map = await get_long_names([new["symbol"].upper()])
    except Exception:
        names_map = {new["symbol"].upper(): None}
    new["long_name"] = names_map.get(new["symbol"].upper())

    # Tags → names
    new["tags"] = await _get_tag_names(new.get("tags", []))

    new = _stringify_id(new) or {}
    return PositionModel(**new)


@app.put("/positions/{position_id}", response_model=PositionModel)
async def update_position(position_id: str, patch: PositionUpdate) -> PositionModel:
    """Patch a position; return the refreshed/enriched document."""
    existing = await db.positions.find_one({"_id": _oid(position_id)})
    if not existing:
        raise HTTPException(status_code=404, detail="Position not found")

    update_doc: Dict[str, Any] = {}

    if patch.symbol is not None:
        update_doc["symbol"] = patch.symbol.upper()
    if patch.quantity is not None:
        update_doc["quantity"] = patch.quantity
    if patch.cost_price is not None:
        update_doc["cost_price"] = patch.cost_price
    if patch.is_closed is not None:
        update_doc["is_closed"] = bool(patch.is_closed)
    if patch.closing_price is not None:
        update_doc["closing_price"] = patch.closing_price
    if patch.tags is not None:
        update_doc["tags"] = await _upsert_tags_return_ids(patch.tags)

    if update_doc:
        update_doc["updated_at"] = datetime.utcnow()
        await db.positions.update_one({"_id": _oid(position_id)}, {"$set": update_doc})

    # Re-fetch and enrich exactly like in GET /positions
    doc = await db.positions.find_one({"_id": _oid(position_id)})
    assert doc is not None

    # Enrich price
    sym = doc["symbol"].upper()
    try:
        price_map = await get_prices([sym])
    except Exception:
        price_map = {sym: None}
    live = price_map.get(sym)
    is_closed = bool(doc.get("is_closed", False))
    closing_price = doc.get("closing_price")
    effective = closing_price if (is_closed and closing_price is not None) else live
    doc["current_price"] = float(effective or 0.0)

    # Long name
    try:
        names_map = await get_long_names([sym])
    except Exception:
        names_map = {sym: None}
    doc["long_name"] = names_map.get(sym)

    # Tags → names
    doc["tags"] = await _get_tag_names(doc.get("tags", []))

    doc = _stringify_id(doc) or {}
    return PositionModel(**doc)


@app.get("/positions/summary")
async def positions_summary() -> Dict[str, float]:
    """Return aggregate totals for market value and unrealized P/L."""
    docs = await db.positions.find().to_list(1000)
    symbols = sorted({d["symbol"].upper() for d in docs})

    try:
        price_map = await get_prices(symbols)
    except Exception:
        price_map = {s: None for s in symbols}

    total_mv = 0.0
    total_pl = 0.0
    for d in docs:
        sym = d["symbol"].upper()
        is_closed = bool(d.get("is_closed", False))
        closing_price = d.get("closing_price")
        live = price_map.get(sym)
        price = closing_price if (is_closed and closing_price is not None) else live
        if price is None:
            continue
        mv = float(price) * float(d["quantity"])
        pl = (float(price) - float(d["cost_price"])) * float(d["quantity"])
        total_mv += mv
        total_pl += pl

    return {"total_market_value": total_mv, "total_unrealized_pl": total_pl}


@app.get("/positions/tags/summary")
async def positions_tags_summary() -> List[Dict[str, float | str]]:
    """Return per-tag rollups: quantity, market value, and unrealized P/L."""
    docs = await db.positions.find().to_list(1000)
    symbols = sorted({d["symbol"].upper() for d in docs})

    try:
        price_map = await get_prices(symbols)
    except Exception:
        price_map = {s: None for s in symbols}

    all_tag_ids = {tid for d in docs for tid in d.get("tags", []) if isinstance(tid, ObjectId)}
    tag_docs = await db.tags.find({"_id": {"$in": list(all_tag_ids)}}).to_list(None)
    tag_map = {t["_id"]: t["name"] for t in tag_docs}

    tag_summary: Dict[str, Dict[str, float | str]] = {}
    for d in docs:
        sym = d["symbol"].upper()
        is_closed = bool(d.get("is_closed", False))
        closing_price = d.get("closing_price")
        live = price_map.get(sym)
        price = closing_price if (is_closed and closing_price is not None) else live
        if price is None:
            continue

        mv = float(price) * float(d["quantity"])
        pl = (float(price) - float(d["cost_price"])) * float(d["quantity"])

        for tid in d.get("tags", []):
            name = tag_map.get(tid)
            if not name:
                continue
            bucket = tag_summary.setdefault(
                name,
                {
                    "tag": name,
                    "total_quantity": 0.0,
                    "total_market_value": 0.0,
                    "total_unrealized_pl": 0.0,
                },
            )
            bucket["total_quantity"] = float(bucket["total_quantity"]) + float(d["quantity"])
            bucket["total_market_value"] = float(bucket["total_market_value"]) + mv
            bucket["total_unrealized_pl"] = float(bucket["total_unrealized_pl"]) + pl

    # Return as a list to keep a stable response shape
    return list(tag_summary.values())
