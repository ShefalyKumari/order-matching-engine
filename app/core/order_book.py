from collections import deque
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
