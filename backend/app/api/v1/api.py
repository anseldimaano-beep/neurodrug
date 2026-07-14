from fastapi import APIRouter

from app.api.v1.endpoints import (
    health, etl, predictions, graph,  # <-- add graph
    auth, assistant, reports, repurposing, validation
)

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(etl.router, prefix="/etl", tags=["etl"])
api_router.include_router(predictions.router, prefix="/predictions", tags=["predictions"])
api_router.include_router(graph.router, prefix="/graph", tags=["graph"])  # <-- add this line
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
# ... other routers