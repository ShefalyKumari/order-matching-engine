import os

files = {}

# 1. app/models/schemas.py
files["app/models/schemas.py"] = """from datetime import datetime, timezone
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
"""

# 2. app/core/order_book.py
files["app/core/order_book.py"] = """from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID
from app.models.schemas import (
    OrderBookDepth,
    OrderBookLevel,
    OrderCreate,
    OrderResponse,
    OrderSide,
    OrderStatus,
    OrderType,
    TradeExecution,
)


class InternalOrder:
    def __init__(self, order_id: UUID, order_in: OrderCreate):
        self.order_id = order_id
        self.symbol = order_in.symbol
        self.side = order_in.side
        self.order_type = order_in.order_type
        self.price = order_in.price if order_in.price else 0.0
        self.quantity = order_in.quantity
        self.filled_quantity = 0.0
        self.status = OrderStatus.PENDING
        self.created_at = datetime.now(timezone.utc)
        self.trades: List[TradeExecution] = []

    @property
    def remaining_quantity(self) -> float:
        return self.quantity - self.filled_quantity

    def to_response(self) -> OrderResponse:
        return OrderResponse(
            order_id=self.order_id,
            symbol=self.symbol,
            side=self.side,
            order_type=self.order_type,
            price=self.price if self.order_type == OrderType.LIMIT else None,
            quantity=self.quantity,
            filled_quantity=self.filled_quantity,
            status=self.status,
            created_at=self.created_at,
            trades=self.trades,
        )


class LimitOrderBook:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.bids: Dict[float, deque] = {}
        self.asks: Dict[float, deque] = {}
        self.orders_map: Dict[UUID, InternalOrder] = {}

    def match_order(self, taker_order: InternalOrder) -> Tuple[InternalOrder, List[TradeExecution]]:
        new_trades: List[TradeExecution] = []

        if taker_order.side == OrderSide.BUY:
            while taker_order.remaining_quantity > 0 and self.asks:
                best_ask = min(self.asks.keys())
                if taker_order.order_type == OrderType.LIMIT and taker_order.price < best_ask:
                    break
                maker_queue = self.asks[best_ask]
                self._execute_queue(taker_order, maker_queue, best_ask, new_trades)
                if not maker_queue:
                    del self.asks[best_ask]

        elif taker_order.side == OrderSide.SELL:
            while taker_order.remaining_quantity > 0 and self.bids:
                best_bid = max(self.bids.keys())
                if taker_order.order_type == OrderType.LIMIT and taker_order.price > best_bid:
                    break
                maker_queue = self.bids[best_bid]
                self._execute_queue(taker_order, maker_queue, best_bid, new_trades)
                if not maker_queue:
                    del self.bids[best_bid]

        if taker_order.remaining_quantity == 0:
            taker_order.status = OrderStatus.FILLED
        elif taker_order.filled_quantity > 0:
            taker_order.status = OrderStatus.PARTIALLY_FILLED

        if taker_order.order_type == OrderType.LIMIT and taker_order.remaining_quantity > 0:
            self._rest_order(taker_order)

        self.orders_map[taker_order.order_id] = taker_order
        return taker_order, new_trades

    def _execute_queue(
        self,
        taker: InternalOrder,
        maker_queue: deque,
        match_price: float,
        trades: List[TradeExecution],
    ):
        while maker_queue and taker.remaining_quantity > 0:
            maker: InternalOrder = maker_queue[0]
            trade_qty = min(taker.remaining_quantity, maker.remaining_quantity)

            trade = TradeExecution(
                maker_order_id=maker.order_id,
                taker_order_id=taker.order_id,
                symbol=self.symbol,
                price=match_price,
                quantity=trade_qty,
            )

            maker.filled_quantity += trade_qty
            taker.filled_quantity += trade_qty
            maker.trades.append(trade)
            taker.trades.append(trade)
            trades.append(trade)

            if maker.remaining_quantity == 0:
                maker.status = OrderStatus.FILLED
                maker_queue.popleft()
            else:
                maker.status = OrderStatus.PARTIALLY_FILLED

    def _rest_order(self, order: InternalOrder):
        book_side = self.bids if order.side == OrderSide.BUY else self.asks
        if order.price not in book_side:
            book_side[order.price] = deque()
        book_side[order.price].append(order)

    def cancel_order(self, order_id: UUID) -> Optional[OrderResponse]:
        order = self.orders_map.get(order_id)
        if not order or order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
            return None

        book_side = self.bids if order.side == OrderSide.BUY else self.asks
        if order.price in book_side:
            try:
                book_side[order.price].remove(order)
                if not book_side[order.price]:
                    del book_side[order.price]
            except ValueError:
                pass

        order.status = OrderStatus.CANCELLED
        return order.to_response()

    def get_depth(self, limit: int = 10) -> OrderBookDepth:
        sorted_bids = sorted(self.bids.keys(), reverse=True)[:limit]
        sorted_asks = sorted(self.asks.keys())[:limit]

        bid_levels = [
            OrderBookLevel(
                price=p,
                quantity=sum(o.remaining_quantity for o in self.bids[p]),
                order_count=len(self.bids[p]),
            )
            for p in sorted_bids
        ]

        ask_levels = [
            OrderBookLevel(
                price=p,
                quantity=sum(o.remaining_quantity for o in self.asks[p]),
                order_count=len(self.asks[p]),
            )
            for p in sorted_asks
        ]

        return OrderBookDepth(
            symbol=self.symbol,
            timestamp=datetime.now(timezone.utc),
            bids=bid_levels,
            asks=ask_levels,
        )
"""

# 3. app/core/engine.py
files["app/core/engine.py"] = """import asyncio
from typing import Dict, List, Set, Tuple
from uuid import UUID, uuid4
from fastapi import WebSocket
from app.core.order_book import InternalOrder, LimitOrderBook
from app.models.schemas import OrderBookDepth, OrderCreate, OrderResponse, TradeExecution


class MatchingEngine:
    def __init__(self):
        self.books: Dict[str, LimitOrderBook] = {}
        self.active_websockets: Set[WebSocket] = set()
        self.lock = asyncio.Lock()

    def get_or_create_book(self, symbol: str) -> LimitOrderBook:
        norm_symbol = symbol.upper()
        if norm_symbol not in self.books:
            self.books[norm_symbol] = LimitOrderBook(norm_symbol)
        return self.books[norm_symbol]

    async def place_order(self, order_in: OrderCreate) -> Tuple[OrderResponse, List[TradeExecution]]:
        async with self.lock:
            book = self.get_or_create_book(order_in.symbol)
            order_id = uuid4()
            internal_order = InternalOrder(order_id, order_in)
            executed_order, trades = book.match_order(internal_order)
            resp = executed_order.to_response()

        if trades:
            asyncio.create_task(self.broadcast_trades(trades))
        return resp, trades

    async def cancel_order(self, symbol: str, order_id: UUID) -> OrderResponse:
        async with self.lock:
            book = self.get_or_create_book(symbol)
            result = book.cancel_order(order_id)
            if not result:
                raise KeyError("Active order not found on book or already filled")
            return result

    def get_depth(self, symbol: str, limit: int = 10) -> OrderBookDepth:
        book = self.get_or_create_book(symbol)
        return book.get_depth(limit)

    async def register_ws(self, ws: WebSocket):
        await ws.accept()
        self.active_websockets.add(ws)

    def unregister_ws(self, ws: WebSocket):
        self.active_websockets.discard(ws)

    async def broadcast_trades(self, trades: List[TradeExecution]):
        if not self.active_websockets:
            return
        payload = [trade.model_dump_json() for trade in trades]
        dead_sockets = set()
        for ws in self.active_websockets:
            try:
                for msg in payload:
                    await ws.send_text(msg)
            except Exception:
                dead_sockets.add(ws)
        self.active_websockets.difference_update(dead_sockets)


engine = MatchingEngine()
"""

# 4. app/api/deps.py
files["app/api/deps.py"] = """from app.core.engine import MatchingEngine, engine


def get_engine() -> MatchingEngine:
    return engine
"""

# 5. app/api/v1/orders.py
files["app/api/v1/orders.py"] = """from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.api.deps import get_engine
from app.core.engine import MatchingEngine
from app.models.schemas import OrderBookDepth, OrderCreate, OrderResponse

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def submit_order(
    order: OrderCreate,
    engine: MatchingEngine = Depends(get_engine),
):
    try:
        response, _ = await engine.place_order(order)
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{symbol}/{order_id}", response_model=OrderResponse)
async def cancel_order(
    symbol: str,
    order_id: UUID,
    engine: MatchingEngine = Depends(get_engine),
):
    try:
        return await engine.cancel_order(symbol, order_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/depth/{symbol}", response_model=OrderBookDepth)
async def get_order_book_depth(
    symbol: str,
    limit: int = Query(default=10, ge=1, le=50),
    engine: MatchingEngine = Depends(get_engine),
):
    return engine.get_depth(symbol, limit)
"""

# 6. app/api/v1/ws.py
files["app/api/v1/ws.py"] = """from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.engine import engine

router = APIRouter(tags=["MarketData WebSocket"])


@router.websocket("/ws/trades")
async def websocket_trades(websocket: WebSocket):
    await engine.register_ws(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        engine.unregister_ws(websocket)
"""

# 7. app/main.py
files["app/main.py"] = """from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.v1 import orders, ws


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="High-Throughput Order Matching & Execution Engine",
    description="Asynchronous limit order book matching engine with microsecond in-memory priority and WebSocket ticker streams.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(orders.router, prefix="/api/v1")
app.include_router(ws.router)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ONLINE", "service": "order-matching-engine"}
"""

# 8. tests/test_engine.py
files["tests/test_engine.py"] = """import pytest
from app.core.engine import MatchingEngine
from app.models.schemas import OrderCreate, OrderSide, OrderStatus, OrderType


@pytest.fixture
def clean_engine():
    return MatchingEngine()


@pytest.mark.asyncio
async def test_limit_order_placement_and_depth(clean_engine):
    order = OrderCreate(
        symbol="BTC-USD",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=60000.0,
        quantity=1.5,
    )
    resp, trades = await clean_engine.place_order(order)
    assert resp.status == OrderStatus.PENDING
    assert len(trades) == 0

    depth = clean_engine.get_depth("BTC-USD")
    assert len(depth.bids) == 1
    assert depth.bids[0].price == 60000.0
    assert depth.bids[0].quantity == 1.5


@pytest.mark.asyncio
async def test_full_cross_matching_execution(clean_engine):
    maker_ask = OrderCreate(
        symbol="BTC-USD",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=65000.0,
        quantity=1.0,
    )
    await clean_engine.place_order(maker_ask)

    taker_bid = OrderCreate(
        symbol="BTC-USD",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=65000.0,
        quantity=1.0,
    )
    resp, trades = await clean_engine.place_order(taker_bid)

    assert resp.status == OrderStatus.FILLED
    assert resp.filled_quantity == 1.0
    assert len(trades) == 1
    assert trades[0].price == 65000.0
    assert trades[0].quantity == 1.0

    depth = clean_engine.get_depth("BTC-USD")
    assert len(depth.bids) == 0
    assert len(depth.asks) == 0


@pytest.mark.asyncio
async def test_partial_fill_behavior(clean_engine):
    await clean_engine.place_order(
        OrderCreate(
            symbol="ETH-USD",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            price=100.0,
            quantity=0.5,
        )
    )

    taker, trades = await clean_engine.place_order(
        OrderCreate(
            symbol="ETH-USD",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price=100.0,
            quantity=2.0,
        )
    )

    assert taker.status == OrderStatus.PARTIALLY_FILLED
    assert taker.filled_quantity == 0.5
    assert len(trades) == 1

    depth = clean_engine.get_depth("ETH-USD")
    assert len(depth.asks) == 0
    assert len(depth.bids) == 1
    assert depth.bids[0].quantity == 1.5
"""

for path, content in files.items():
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Created: {path}")

print("\\nAll project files written successfully!")