import asyncio
import hmac
import time
from typing import Dict, List, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import Settings, get_settings


def get_client_ip(request: Request) -> str:
    """
    Resolve client IP, preferring the first value from X-Forwarded-For when present.
    """

    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    client = request.client
    return client.host if client else "unknown"


class RateLimiter:
    """
    Simple in-memory sliding window rate limiter keyed by client IP.
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: Dict[str, List[float]] = {}
        self._lock = asyncio.Lock()

    async def allow(self, identity: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window_seconds

        async with self._lock:
            hits = self._hits.get(identity, [])
            hits = [ts for ts in hits if ts >= window_start]
            if len(hits) >= self.max_requests:
                self._hits[identity] = hits
                return False

            hits.append(now)
            self._hits[identity] = hits
            return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60) -> None:
        super().__init__(app)
        self.limiter = RateLimiter(max_requests=max_requests, window_seconds=window_seconds)

    async def dispatch(self, request: Request, call_next):
        client_ip = get_client_ip(request)
        allowed = await self.limiter.allow(client_ip)

        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too many requests"},
            )

        return await call_next(request)


async def verify_api_key(
    settings: Settings = Depends(get_settings), x_api_key: Optional[str] = Header(None, alias="X-API-KEY")
) -> None:
    """
    Verify API key using constant-time comparison.
    """

    if x_api_key is None or not hmac.compare_digest(str(x_api_key), settings.api_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
