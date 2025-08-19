from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class TagModel(BaseModel):
    id: str
    name: str


class PositionCreate(BaseModel):
    symbol: str
    quantity: float
    cost_price: float
    tags: List[str] = []
    is_closed: bool = False
    closing_price: Optional[float] = None


class PositionUpdate(BaseModel):
    symbol: Optional[str] = None
    quantity: Optional[float] = None
    cost_price: Optional[float] = None
    tags: Optional[List[str]] = None
    is_closed: Optional[bool] = None
    closing_price: Optional[float] = None


class PositionModel(BaseModel):
    id: str = Field(alias="_id")  # ✅ use alias for Mongo _id
    symbol: str
    quantity: float
    cost_price: float
    tags: List[str] = []
    current_price: float = 0.0
    is_closed: bool = False
    closing_price: Optional[float] = None

    # Enrichment
    long_name: Optional[str] = None
    intraday_change: Optional[float] = None
    intraday_change_pct: Optional[float] = None
