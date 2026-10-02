import asyncio
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
