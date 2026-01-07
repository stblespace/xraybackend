import logging
from typing import Dict

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.anti_sharing import ConnectionLimiter
from app.config import Settings, get_settings
from app.logging import configure_logging
from app.schemas import HealthResponse, UserRequest
from app.security import RateLimitMiddleware, verify_api_key
from app.xray_client import XrayClient, XrayClientError

settings: Settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Xray Control API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(RateLimitMiddleware)


def _get_client() -> XrayClient:
    client: XrayClient = getattr(app.state, "xray_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Xray client not initialized"
        )
    return client


@app.on_event("startup")
async def startup_event() -> None:
    app.state.connection_limiter = ConnectionLimiter(settings.max_connections_per_user)
    client = XrayClient(
        host=settings.xray_api_host,
        port=settings.xray_api_port,
        inbound_tag=settings.xray_inbound_tag,
    )
    app.state.xray_client = client

    try:
        await client.start()
    except XrayClientError as exc:
        logger.warning("xray_unavailable_on_startup", extra={"error": str(exc)})


@app.on_event("shutdown")
async def shutdown_event() -> None:
    client: XrayClient = getattr(app.state, "xray_client", None)
    if client:
        await client.close()


@app.exception_handler(XrayClientError)
async def xray_error_handler(_: Request, exc: XrayClientError):
    logger.error("xray_error", extra={"error": str(exc)})
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": "Xray unavailable"}
    )


@app.post("/add_user")
async def add_user(payload: UserRequest, _: None = Depends(verify_api_key)) -> Dict[str, str]:
    client = _get_client()

    try:
        created = await client.add_user(str(payload.uuid))
    except XrayClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Xray unavailable"
        ) from exc

    logger.info("user_added", extra={"uuid": str(payload.uuid), "created": created})
    return {"status": "ok"}


@app.post("/remove_user")
async def remove_user(payload: UserRequest, _: None = Depends(verify_api_key)) -> Dict[str, str]:
    client = _get_client()

    try:
        removed = await client.remove_user(str(payload.uuid))
    except XrayClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Xray unavailable"
        ) from exc

    logger.info("user_removed", extra={"uuid": str(payload.uuid), "removed": removed})
    return {"status": "ok"}


@app.get("/health", response_model=HealthResponse)
async def health() -> JSONResponse:
    client = getattr(app.state, "xray_client", None)
    healthy = False

    if client:
        healthy = await client.check_health()

    status_text = "ok" if healthy else "degraded"
    http_status = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(status_code=http_status, content={"status": status_text})
