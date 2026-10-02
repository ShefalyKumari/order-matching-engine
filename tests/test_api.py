import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ONLINE", "service": "order-matching-engine"}


@pytest.mark.asyncio
async def test_create_and_fetch_depth_via_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Place LIMIT BUY order
        buy_payload = {
            "symbol": "ETH-USD",
            "side": "BUY",
            "order_type": "LIMIT",
            "price": 3200.0,
            "quantity": 2.5,
        }
        res = await ac.post("/api/v1/orders/", json=buy_payload)
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "PENDING"
        assert data["price"] == 3200.0
        order_id = data["order_id"]

        # Fetch Order Book Depth
        depth_res = await ac.get("/api/v1/orders/depth/ETH-USD")
        assert depth_res.status_code == 200
        depth = depth_res.json()
        assert len(depth["bids"]) >= 1
        assert depth["bids"][0]["price"] == 3200.0

        # Cancel the order
        cancel_res = await ac.delete(f"/api/v1/orders/ETH-USD/{order_id}")
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == "CANCELLED"