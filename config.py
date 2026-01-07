from functools import lru_cache
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """
    Centralized configuration pulled from environment variables.
    """

    api_key: str = Field(..., env="API_KEY")
    xray_grpc_host: str = Field("127.0.0.1", env="XRAY_GRPC_HOST")
    xray_grpc_port: int = Field(10085, env="XRAY_GRPC_PORT")
    xray_account_type_url: str = Field(
        "type.googleapis.com/xray.proxy.vless.Account", env="XRAY_ACCOUNT_TYPE_URL"
    )
    xray_handler_service: str = Field(
        "xray.app.proxyman.command.HandlerService", env="XRAY_HANDLER_SERVICE"
    )
    vless_flow: str = Field("", env="XRAY_VLESS_FLOW")
    vless_encryption: str = Field("none", env="XRAY_VLESS_ENCRYPTION")

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
