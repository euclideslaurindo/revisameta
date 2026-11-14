import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Color = Literal["yellow", "green", "blue", "pink"]


class AttachPdfIn(BaseModel):
    upload_id: uuid.UUID


class PdfOut(BaseModel):
    id: uuid.UUID
    report_id: uuid.UUID
    original_filename: str
    size_bytes: int
    page_count: int | None
    text_status: str
    created_at: datetime


class PdfViewOut(PdfOut):
    url: str
    expires_in: int


class SearchHit(BaseModel):
    page: int
    snippet: str


class Rect(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(ge=0, le=1)
    h: float = Field(ge=0, le=1)


class AnnotationIn(BaseModel):
    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=5000)
    rects: list[Rect] = Field(default_factory=list, max_length=200)
    note: str | None = Field(default=None, max_length=2000)
    color: Color = "yellow"


class AnnotationUpdate(BaseModel):
    version: int
    note: str | None = Field(default=None, max_length=2000)
    color: Color | None = None


class AnnotationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pdf_file_id: uuid.UUID
    user_id: uuid.UUID
    page: int
    quote: str
    rects: list[Rect]
    note: str | None
    color: str
    version: int
    created_at: datetime
