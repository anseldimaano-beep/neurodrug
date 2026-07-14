from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import time
from collections import defaultdict
from typing import Dict, List
from app.core.config import settings


class RateLimiter:
    def __init__(self, requests_per_minute: int = None):
        self.requests_per_minute = requests_per_minute or settings.RATE_LIMIT_PER_MINUTE
        self.requests: Dict[str, List[float]] = defaultdict(list)

    async def check(self, request: Request):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window = self.requests[client_ip]
        window[:] = [t for t in window if now - t < 60]
        if len(window) >= self.requests_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Retry after 60s."
            )
        window.append(now)


class APIKeyBearer(HTTPBearer):
    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)

    async def __call__(self, request: Request):
        credentials: HTTPAuthorizationCredentials = await super().__call__(request)
        if credentials:
            if credentials.scheme != "ApiKey":
                raise HTTPException(status_code=403, detail="Invalid authentication scheme")
            if not self.verify_key(credentials.credentials):
                raise HTTPException(status_code=403, detail="Invalid API key")
            return credentials.credentials
        raise HTTPException(status_code=403, detail="Invalid authorization code")

    def verify_key(self, key: str) -> bool:
        return key.startswith("ndk_") and len(key) > 20


rate_limiter = RateLimiter()
