# backend/app/models.py

from datetime import datetime
from typing import List, Optional

from bson import ObjectId
from pydantic import BaseModel, Field


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, info=None):
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str):
            try:
                return ObjectId(v)
            except Exception:
                raise ValueError("Invalid ObjectId")
        raise TypeError("ObjectId or valid string required")


class TagModel(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(..., min_length=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        validate_by_name = True
        json_encoders = {ObjectId: str}


class PositionModel(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    symbol: str = Field(..., min_length=1)
    quantity: float = Field(..., gt=0)
    cost_price: float = Field(..., ge=0)
    current_price: float = Field(..., ge=0)
    tags: List[str] = Field(default_factory=list)  # ← return tag names, not ObjectIds
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        validate_by_name = True
        json_encoders = {ObjectId: str}


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1)


class PositionCreate(BaseModel):
    symbol: str = Field(..., min_length=1)
    quantity: float = Field(..., gt=0)
    cost_price: float = Field(..., ge=0)
    tags: Optional[List[str]] = []  # accept names here


class SummaryModel(BaseModel):
    total_market_value: float
    total_unrealized_pl: float


class TagSummaryModel(BaseModel):
    tag: str
    total_quantity: float
    total_market_value: float
    total_unrealized_pl: float
