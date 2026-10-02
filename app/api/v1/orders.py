from uuid import UUID
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
