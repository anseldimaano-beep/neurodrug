from fastapi import APIRouter

from app.api.v1.endpoints import (
    health, etl, predictions, graph,
    auth, assistant, reports, repurposing, validation, training
)

api_router = APIRouter()

api_router.include_router(health.router,       prefix="/health",       tags=["health"])
api_router.include_router(auth.router,         prefix="/auth",         tags=["auth"])
api_router.include_router(etl.router,          prefix="/etl",          tags=["etl"])
api_router.include_router(predictions.router,  prefix="/predictions",  tags=["predictions"])
api_router.include_router(graph.router,        prefix="/graph",        tags=["graph"])
api_router.include_router(validation.router,   prefix="/validation",   tags=["validation"])
api_router.include_router(repurposing.router,  prefix="/repurposing",  tags=["repurposing"])
api_router.include_router(reports.router,      prefix="/reports",      tags=["reports"])
api_router.include_router(assistant.router,    prefix="/assistant",    tags=["assistant"])
api_router.include_router(training.router,     prefix="/training",     tags=["training"])
