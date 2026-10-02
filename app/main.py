from contextlib import asynccontextmanager
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
