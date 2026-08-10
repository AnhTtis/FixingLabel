from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PageGeometry:
    pdf_width: float
    pdf_height: float
    image_width: float
    image_height: float


@dataclass(frozen=True)
class ViewportTransform:
    scale: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0


def pdf_to_image_bbox(bbox: list[float], geometry: PageGeometry) -> list[float]:
    scale_x = geometry.image_width / geometry.pdf_width
    scale_y = geometry.image_height / geometry.pdf_height
    x0, y0, x1, y1 = bbox
    return [x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y]


def image_to_pdf_bbox(bbox: list[float], geometry: PageGeometry) -> list[float]:
    scale_x = geometry.pdf_width / geometry.image_width
    scale_y = geometry.pdf_height / geometry.image_height
    x0, y0, x1, y1 = bbox
    return [x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y]


def image_to_viewport_bbox(bbox: list[float], viewport: ViewportTransform) -> list[float]:
    x0, y0, x1, y1 = bbox
    return [
        x0 * viewport.scale + viewport.offset_x,
        y0 * viewport.scale + viewport.offset_y,
        x1 * viewport.scale + viewport.offset_x,
        y1 * viewport.scale + viewport.offset_y,
    ]


def viewport_to_image_bbox(bbox: list[float], viewport: ViewportTransform) -> list[float]:
    x0, y0, x1, y1 = bbox
    return [
        (x0 - viewport.offset_x) / viewport.scale,
        (y0 - viewport.offset_y) / viewport.scale,
        (x1 - viewport.offset_x) / viewport.scale,
        (y1 - viewport.offset_y) / viewport.scale,
    ]
