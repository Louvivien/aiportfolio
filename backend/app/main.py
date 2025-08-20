# backend/app/main.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Union

from bson import ObjectId
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .database import db
from .models import PositionCreate, PositionModel, PositionUpdate, TagModel
from .price_service import get_prices

app = FastAPI(title="Portfolio Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _oid(s: Union[str, ObjectId]) -> Union[ObjectId, str]:
    if isinstance(s, ObjectId):
        return s
    return ObjectId(s) if ObjectId.is_valid(s) else s


def _as_true(v) -> bool:
    if v is True:
        return True
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "y", "on"}
    if isinstance(v, (int, float)):
        return v == 1
    return False


def _stringify_id(d: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if d is None:
        return None
    out: Dict[str, Any] = dict(d)
    if "_id" in out and isinstance(out["_id"], ObjectId):
        out["_id"] = str(out["_id"])
    return out


async def _get_tag_names(tag_ids: List[ObjectId]) -> List[str]:
    if not tag_ids:
        return []
    docs = await db.tags.find({"_id": {"$in": tag_ids}}).to_list(len(tag_ids))
    name_by_id = {d["_id"]: d["name"] for d in docs}
    return [name_by_id.get(tid, "") for tid in tag_ids if tid in name_by_id]


async def _upsert_tags_return_ids(names: List[str]) -> List[ObjectId]:
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


@app.get("/tags", response_model=List[TagModel])
async def read_tags():
    docs = await db.tags.find().to_list(None)
    return [TagModel(id=str(d["_id"]), name=d["name"]) for d in docs]


@app.get("/positions", response_model=List[PositionModel])
async def read_positions():
    docs = await db.positions.find().to_list(1000)
    symbols = sorted({d["symbol"].upper() for d in docs})

    try:
        price_map = await get_prices(symbols)
    except Exception:
        price_map = {s: {} for s in symbols}

    out = []
    for d in docs:
        sym = d["symbol"].upper()
        p = price_map.get(sym, {})

        is_closed = _as_true(d.get("is_closed", False))
        closing_price = d.get("closing_price")
        live = p.get("current")
        effective = closing_price if (is_closed and closing_price is not None) else live
        d["current_price"] = float(effective or 0.0)

        # enrich from price map
        d["long_name"] = p.get("long_name")
        d["intraday_change"] = p.get("change")
        d["intraday_change_pct"] = p.get("change_pct")

        d["tags"] = await _get_tag_names(d.get("tags", []))
        d = _stringify_id(d)
        out.append(PositionModel(**d))
    return out


@app.post("/positions", response_model=PositionModel)
async def create_position(position: PositionCreate):
    now = datetime.utcnow()
    tag_ids = await _upsert_tags_return_ids(position.tags or [])

    doc = {
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

    try:
        price_map = await get_prices([new["symbol"].upper()])
    except Exception:
        price_map = {new["symbol"].upper(): {}}

    sym = new["symbol"].upper()
    p = price_map.get(sym, {})
    is_closed = _as_true(new.get("is_closed", False))
    closing_price = new.get("closing_price")
    live = p.get("current")
    effective = closing_price if (is_closed and closing_price is not None) else live
    new["current_price"] = float(effective or 0.0)
    new["long_name"] = p.get("long_name")
    new["intraday_change"] = p.get("change")
    new["intraday_change_pct"] = p.get("change_pct")

    new["tags"] = await _get_tag_names(new.get("tags", []))
    new = _stringify_id(new)
    return PositionModel(**new)


@app.put("/positions/{position_id}", response_model=PositionModel)
async def update_position(position_id: str, patch: PositionUpdate):
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

    doc = await db.positions.find_one({"_id": _oid(position_id)})

    try:
        price_map = await get_prices([doc["symbol"].upper()])
    except Exception:
        price_map = {doc["symbol"].upper(): {}}

    sym = doc["symbol"].upper()
    p = price_map.get(sym, {})
    is_closed = _as_true(doc.get("is_closed", False))
    closing_price = doc.get("closing_price")
    live = p.get("current")
    effective = closing_price if (is_closed and closing_price is not None) else live
    doc["current_price"] = float(effective or 0.0)
    doc["long_name"] = p.get("long_name")
    doc["intraday_change"] = p.get("change")
    doc["intraday_change_pct"] = p.get("change_pct")
    doc["tags"] = await _get_tag_names(doc.get("tags", []))
    doc = _stringify_id(doc)
    return PositionModel(**doc)


# ──────────────────────────────────────────────────────────────
# Portfolio summary
# ──────────────────────────────────────────────────────────────
@app.get("/positions/summary")
async def positions_summary():
    """
    Return total market value and unrealized P/L across all *open* positions.
    Closed positions are excluded from both totals.
    """
    docs = await db.positions.find().to_list(1000)
    symbols = sorted({d["symbol"].upper() for d in docs})

    try:
        price_map = await get_prices(symbols)  # {SYM: {"current": ..., ...}}
    except Exception:
        price_map = {s: {} for s in symbols}

    total_mv = 0.0
    total_pl = 0.0

    for d in docs:
        if _as_true(d.get("is_closed", False)):
            continue  # exclude closed from totals

        sym = d["symbol"].upper()
        p = price_map.get(sym, {})
        price = p.get("current")
        if price is None:
            continue
        qty = float(d.get("quantity", 0.0))
        cost = float(d.get("cost_price", 0.0))
        total_mv += price * qty
        total_pl += (price - cost) * qty

    return {"total_market_value": total_mv, "total_unrealized_pl": total_pl}


# ADD THIS near the other routes in backend/app/main.py


@app.get("/positions/summary/debug")
async def positions_summary_debug():
    """
    Per-position contribution to Total Market Value for OPEN positions only.
    """
    docs = await db.positions.find().to_list(1000)
    symbols = sorted({d["symbol"].upper() for d in docs})

    try:
        price_map = await get_prices(symbols)  # {SYM: {"current": ...}}
    except Exception:
        price_map = {s: {} for s in symbols}

    rows = []
    total = 0.0
    for d in docs:
        is_closed = _as_true(d.get("is_closed", False))
        if is_closed:
            continue

        sym = d["symbol"].upper()
        qty = float(d.get("quantity", 0.0))
        price = price_map.get(sym, {}).get("current")
        if price is None:
            rows.append(
                {
                    "symbol": sym,
                    "qty": qty,
                    "used_price": None,
                    "subtotal": 0.0,
                    "note": "missing live price",
                }
            )
            continue

        price_f = float(price)
        subtotal = price_f * qty
        total += subtotal
        rows.append(
            {
                "symbol": sym,
                "qty": qty,
                "used_price": price_f,
                "subtotal": subtotal,
                "note": "",
            }
        )

    return {"total_market_value": total, "rows": rows}


@app.get("/positions/tags/summary")
async def positions_tags_summary():
    docs = await db.positions.find().to_list(1000)
    symbols = sorted({d["symbol"].upper() for d in docs})

    try:
        price_map = await get_prices(symbols)  # {SYM: {"current": ..., ...}}
    except Exception:
        price_map = {s: {} for s in symbols}

    # map tag_id -> tag name
    all_tag_ids = {tid for d in docs for tid in d.get("tags", [])}
    tag_docs = await db.tags.find({"_id": {"$in": list(all_tag_ids)}}).to_list(None)
    tag_map = {t["_id"]: t["name"] for t in tag_docs}

    out: dict[str, dict] = {}
    for d in docs:
        if _as_true(d.get("is_closed", False)):
            continue  # exclude closed from tag totals too

        sym = d["symbol"].upper()
        p = price_map.get(sym, {})
        price = p.get("current")
        if price is None:
            continue

        qty = float(d.get("quantity", 0.0))
        cost = float(d.get("cost_price", 0.0))
        mv = price * qty
        pl = (price - cost) * qty

        for tid in d.get("tags", []):
            name = tag_map.get(tid)
            if not name:
                continue
            bucket = out.setdefault(
                name,
                {
                    "tag": name,
                    "total_quantity": 0.0,
                    "total_market_value": 0.0,
                    "total_unrealized_pl": 0.0,
                },
            )
            bucket["total_quantity"] += qty
            bucket["total_market_value"] += mv
            bucket["total_unrealized_pl"] += pl

    return list(out.values())
