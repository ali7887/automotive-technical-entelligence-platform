import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class WorkspaceUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class WorkspaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    created_at: datetime
