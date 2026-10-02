import pytest
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
