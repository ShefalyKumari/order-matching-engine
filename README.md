# High-Throughput Order Matching & Execution Engine

An asynchronous, low-latency electronic trading and order-matching backend engineered with **FastAPI** and **Python 3.11**, simulating modern equity and cryptocurrency exchange infrastructure. 

The service maintains an in-memory, price-time priority Limit Order Book (LOB) executing trades with sub-millisecond overhead, combined with real-time market data streaming over WebSockets.

---

## Architecture Overview

```text
       +---------------------------------------------+
       |             Client Applications             |
       +---------------------+-----------------------+
                             |
              HTTP POST / DELETE / GET | WebSocket Feed
                             v
       +---------------------------------------------+
       |             FastAPI ASGI Layer              |
       |  - Strict Pydantic v2 Schema Validation     |
       |  - Async Route Handlers & Dependency Inj.   |
       +---------------------+-----------------------+
                             |
                      asyncio.Lock
                             v
       +---------------------------------------------+
       |        In-Memory Matching Engine Core       |
       |  - LimitOrderBook (Sorted Price Ladders)    |
       |  - Price-Time Priority & FIFO Deques        |
       |  - Execution Engine (Cross, Partial, Rest)  |
       +---------------------+-----------------------+
                             |
               Real-Time Trade Broadcast
                             v
       +---------------------------------------------+
       |      WebSocket Hub (/ws/trades Stream)      |
       |  - Asynchronous Connection Registry         |
       |  - Dead-Socket Pruning & Fan-out Events     |
       +---------------------------------------------+

       order-matching-engine/
├── app/
│   ├── api/
│   │   ├── deps.py               # Dependency injection providers
│   │   ├── router.py             # Route registry
│   │   └── v1/
│   │       ├── orders.py         # REST endpoints for orders and depth
│   │       └── ws.py             # WebSocket market stream endpoint
│   ├── core/
│   │   ├── engine.py             # Matching engine & WebSocket broadcaster
│   │   └── order_book.py         # Limit Order Book data structures
│   ├── models/
│   │   └── schemas.py            # Pydantic v2 schemas and validators
│   └── main.py                   # Application entrypoint & lifespan events
├── tests/
│   ├── test_engine.py            # Matching engine core unit tests
│   └── test_api.py               # Async HTTP & integration tests
├── Dockerfile                    # Container configuration
├── requirements.txt              # Production and test dependencies
└── README.md