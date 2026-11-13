import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UploadCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)
    content_type: str = Field(default="application/pdf", max_length=100)


class UploadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    size_bytes: int
    part_size: int
    part_count: int
    status: str
    error_code: str | None
    stored_file_id: uuid.UUID | None
    job_id: uuid.UUID | None
    expires_at: datetime


class UploadState(UploadOut):
    """Includes which parts the storage already has, so the browser can resume."""

    uploaded_parts: list[int] = Field(default_factory=list)


class PartUrlsIn(BaseModel):
    part_numbers: list[int] = Field(min_length=1, max_length=100)


class PartUrl(BaseModel):
    part_number: int
    url: str


class DownloadUrl(BaseModel):
    url: str
    expires_in: int


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    status: str
    progress: int
    result: dict[str, object] | None
    error_code: str | None
    updated_at: datetime
