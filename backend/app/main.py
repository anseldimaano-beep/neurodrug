"""NeuroDrug v4 — Unified Drug Repurposing AI Platform."""
from contextlib import asynccontextmanager
from starlette.responses import Response
from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import ORJSONResponse
from prometheus_client import make_asgi_app
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
import time

from app.core.config import settings
from app.core.logging import configure_logging, logger
from app.core.security import rate_limiter
from app.core.metrics import REQUEST_COUNT, REQUEST_LATENCY, ACTIVE_REQUESTS, BUILD_INFO
from app.middleware.security import SecurityHeadersMiddleware
from app.api.v1.api import api_router
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    BUILD_INFO.info({
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    })
    logger.info(f"NeuroDrug v{settings.VERSION} starting [{settings.ENVIRONMENT}]")
    yield
    logger.info("NeuroDrug shutting down")
    await engine.dispose()


def create_application() -> FastAPI:
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[FastApiIntegration()],
            traces_sample_rate=0.1,
        )

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="Production-grade drug repurposing AI platform — NeuroDrug v4",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # Trusted hosts
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "*.neurodrug.local", "*.up.railway.app", "*"],
    )

    # ------------------------------------------------------------------ #
    # CORS — custom implementation that unconditionally adds the header.  #
    # Starlette's built-in CORSMiddleware has an early-return when the    #
    # Origin header is absent, which happens when browsers drop it after  #
    # following a 307 redirect (trailing-slash normalisation).  This      #
    # middleware handles both the OPTIONS preflight and actual requests    #
    # without that limitation.                                            #
    # ------------------------------------------------------------------ #
    @app.middleware("http")
    async def cors_middleware(request: Request, call_next):
        if request.method == "OPTIONS":
            response = Response(status_code=200)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Access-Control-Max-Age"] = "86400"
            return response
        response = await call_next(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        return response

    # Prometheus metrics middleware
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        ACTIVE_REQUESTS.inc()
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        ACTIVE_REQUESTS.dec()
        endpoint = request.url.path
        REQUEST_COUNT.labels(request.method, endpoint, response.status_code).inc()
        REQUEST_LATENCY.labels(request.method, endpoint).observe(elapsed)
        response.headers["X-Process-Time"] = f"{elapsed:.4f}"
        return response

    # Rate limiting middleware
    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if not request.url.path.startswith("/metrics"):
            await rate_limiter.check(request)
        return await call_next(request)

    # Routes
    app.include_router(api_router, prefix=settings.API_V1_STR)

    # Prometheus /metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    @app.get("/health", tags=["health"])
    async def root_health():
        return {"status": "healthy", "version": settings.VERSION}

    return app


app = create_application()
