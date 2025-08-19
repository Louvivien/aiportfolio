# backend/app/models.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PositionUpdate(BaseModel):
    symbol: Optional[str] = None
    quantity: Optional[float] = None
    cost_price: Optional[float] = None
    tags: Optional[List[str]] = None
    is_closed: Optional[bool] = None
    closing_price: Optional[float] = None


class TagModel(BaseModel):
    id: str = Field(alias="_id")
    name: str
    model_config = ConfigDict(populate_by_name=True)


class PositionCreate(BaseModel):
    symbol: str
    quantity: float
    cost_price: float
    tags: list[str] = []
    # closed position fields
    is_closed: bool = False
    closing_price: float | None = None


class PositionModel(PositionCreate):
    id: str = Field(alias="_id")
    current_price: float = 0.0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    long_name: str | None = None
    model_config = ConfigDict(populate_by_name=True)


class SummaryModel(BaseModel):
    total_market_value: float
    total_unrealized_pl: float
