from datetime import datetime

from pydantic import BaseModel, Field

from app.models import JobState


class JobCreate(BaseModel):
    payload: dict = Field(default_factory=dict, description="Arbitrary JSON payload passed to the worker.")


class JobResponse(BaseModel):
    id: str
    state: JobState
    payload: dict | None = None
    result: dict | None = None
    error: str | None = None
    retry_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobSubmitResponse(BaseModel):
    id: str
    state: JobState
    created: bool = Field(description="True if a new job was created; false if an existing job was returned due to idempotency.")
