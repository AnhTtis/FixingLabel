from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnnotationMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coord_space: Literal["pdf"] = "pdf"
    version: int = Field(default=1, ge=1)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AnnotationElement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    score: float | None = Field(default=None, ge=0, le=1)
    locked: bool = False
    hidden: bool = False
    notes: str = ""
    text: str | None = None
    reading_order: int | None = None

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        if len(value) != 4:
            raise ValueError("bbox must contain exactly four coordinates")
        x0, y0, x1, y1 = value
        if x0 >= x1 or y0 >= y1:
            raise ValueError("bbox coordinates must satisfy x0 < x1 and y0 < y1")
        return value


class AnnotationPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    elements: list[AnnotationElement] = Field(default_factory=list)


class AnnotationDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    source_pdf: str = Field(min_length=1)
    meta: AnnotationMeta
    pages: list[AnnotationPage] = Field(default_factory=list)


class DocumentSummary(BaseModel):
    doc_id: str
    source_pdf: str
    page_count: int
    annotation_version: int
    labels: dict


class BBoxPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["update_bbox"]
    page: int = Field(ge=1)
    element_id: str = Field(min_length=1)
    bbox: list[float] = Field(min_length=4, max_length=4)


class LabelPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["update_label"]
    page: int = Field(ge=1)
    element_id: str = Field(min_length=1)
    label: str = Field(min_length=1)


class CreatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["create_element"]
    page: int = Field(ge=1)
    element: AnnotationElement


class DeletePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["delete_element"]
    page: int = Field(ge=1)
    element_id: str = Field(min_length=1)


PatchOperation = Annotated[BBoxPatch | LabelPatch | CreatePatch | DeletePatch, Field(discriminator="op")]
