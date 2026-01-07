from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class UserRequest(BaseModel):
    uuid: UUID

    class Config:
        anystr_strip_whitespace = True
        extra = "forbid"


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
