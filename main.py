from fastapi import Depends, FastAPI, Header, HTTPException, status

from config import get_settings
from schemas import UserRequest
from xray_client import XrayClient, XrayClientError

settings = get_settings()
app = FastAPI(title="Xray Control API", version="1.0.0")


async def require_api_key(x_api_key: str = Header(None, alias="X-API-KEY")) -> None:
    """
    Reject requests without a valid API key.
    """

    if x_api_key is None or x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


@app.on_event("startup")
async def startup_event() -> None:
    client = XrayClient(
        host=settings.xray_grpc_host,
        port=settings.xray_grpc_port,
        account_type_url=settings.xray_account_type_url,
        handler_service=settings.xray_handler_service,
        flow=settings.vless_flow,
        encryption=settings.vless_encryption,
    )
    await client.start()
    app.state.xray_client = client


@app.on_event("shutdown")
async def shutdown_event() -> None:
    client = getattr(app.state, "xray_client", None)
    if client:
        await client.close()


def _client() -> XrayClient:
    client: XrayClient = getattr(app.state, "xray_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Xray client not initialized",
        )
    return client


@app.post("/add_user")
async def add_user(payload: UserRequest, _: None = Depends(require_api_key)) -> dict:
    try:
        await _client().add_user(str(payload.uuid))
    except XrayClientError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return {"status": "ok"}


@app.post("/remove_user")
async def remove_user(payload: UserRequest, _: None = Depends(require_api_key)) -> dict:
    try:
        await _client().remove_user(str(payload.uuid))
    except XrayClientError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return {"status": "ok"}
