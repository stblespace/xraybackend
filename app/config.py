from functools import lru_cache
from typing import Set

from pydantic import BaseSettings, Field, validator


LOCALHOST_VALUES: Set[str] = {"127.0.0.1", "localhost", "::1"}


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables.
    """

    api_key: str = Field(..., env="API_KEY")
    xray_api_host: str = Field("127.0.0.1", env="XRAY_API_HOST")
    xray_api_port: int = Field(10085, env="XRAY_API_PORT")
    xray_inbound_tag: str = Field("vless-reality", env="XRAY_INBOUND_TAG")
    max_connections_per_user: int = Field(0, env="MAX_CONNECTIONS_PER_USER")
    log_level: str = Field("INFO", env="LOG_LEVEL")

    class Config:
        env_file = ".env"
        case_sensitive = False

    @validator("api_key")
    def validate_api_key(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("API_KEY must be provided")
        return value

    @validator("xray_api_host")
    def validate_xray_api_host(cls, value: str) -> str:
        host = value.strip()
        if host not in LOCALHOST_VALUES:
            raise ValueError("XRAY_API_HOST must remain on localhost for security")
        return host

    @validator("xray_inbound_tag")
    def validate_inbound_tag(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("XRAY_INBOUND_TAG cannot be empty")
        return value.strip()

    @validator("log_level")
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @validator("max_connections_per_user")
    def normalize_max_connections(cls, value: int) -> int:
        return max(0, value)


@lru_cache()
def get_settings() -> Settings:
    return Settings()
