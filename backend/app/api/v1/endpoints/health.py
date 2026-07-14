from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.api.deps import get_db
from app.core.config import settings
import redis.asyncio as aioredis

router = APIRouter()


@router.get("/", summary="Liveness probe")
async def health_check():
    return {"status": "healthy", "version": settings.VERSION, "service": settings.PROJECT_NAME}


@router.get("/ready", summary="Readiness probe")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    result = {"status": "ready", "checks": {}}
    try:
        await db.execute(text("SELECT 1"))
        result["checks"]["postgres"] = "ok"
    except Exception as e:
        result["checks"]["postgres"] = f"error: {e}"
        result["status"] = "degraded"

    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        result["checks"]["redis"] = "ok"
    except Exception as e:
        result["checks"]["redis"] = f"error: {e}"
        result["status"] = "degraded"

    return result
