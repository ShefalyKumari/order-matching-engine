from fastapi import APIRouter, WebSocket, WebSocketDisconnect
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
