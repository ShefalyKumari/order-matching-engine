from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, field_validator


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class OrderCreate(BaseModel):
    symbol: str = Field(..., examples=["BTC-USD"], min_length=3, max_length=12)
    side: OrderSide
    order_type: OrderType
    price: Optional[float] = Field(None, gt=0, description="Required for LIMIT orders")
    quantity: float = Field(..., gt=0, description="Order quantity")

    @field_validator("price")
    @classmethod
    def validate_price_for_limit(cls, v, info):
        if info.data.get("order_type") == OrderType.LIMIT and (v is None or v <= 0):
            raise ValueError("Price is strictly required and must be > 0 for LIMIT orders")
        return v


class TradeExecution(BaseModel):
    trade_id: UUID = Field(default_factory=uuid4)
    maker_order_id: UUID
    taker_order_id: UUID
    symbol: str
    price: float
    quantity: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OrderResponse(BaseModel):
    order_id: UUID
    symbol: str
    side: OrderSide
    order_type: OrderType
    price: Optional[float]
    quantity: float
    filled_quantity: float = 0.0
    status: OrderStatus
    created_at: datetime
    trades: List[TradeExecution] = []


class OrderBookLevel(BaseModel):
    price: float
    quantity: float
    order_count: int


class OrderBookDepth(BaseModel):
    symbol: str
    timestamp: datetime
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]
