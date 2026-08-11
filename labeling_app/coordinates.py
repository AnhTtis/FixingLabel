from __future__ import annotations

import copy
from typing import Any

TARGET_MAX_DIM = 896.0
PDF_COORDINATE_SPACE = "pdf_xyxy"
SCALED_896_COORDINATE_SPACE = "scaled_896_xyxy"


def get_page_scale_896(page_width: float, page_height: float) -> float:
    width = float(page_width)
    height = float(page_height)
    longest_side = max(width, height)
    if longest_side <= 0:
        raise ValueError("Page dimensions must be positive.")
    return TARGET_MAX_DIM / longest_side



def get_scaled_page_size(page_width: float, page_height: float) -> tuple[float, float]:
    scale = get_page_scale_896(page_width, page_height)
    return float(page_width) * scale, float(page_height) * scale



def _coerce_bbox(bbox: Any) -> list[float]:
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError(f"Invalid bbox payload: {bbox!r}")
    return [float(value) for value in bbox]



def _round_bbox(bbox: list[float]) -> list[float]:
    return [round(float(value), 2) for value in bbox]



def bbox_896_to_pdf(bbox: list[float], page_width: float, page_height: float) -> list[float]:
    scale = get_page_scale_896(page_width, page_height)
    return _round_bbox([value / scale for value in _coerce_bbox(bbox)])



def bbox_pdf_to_896(bbox: list[float], page_width: float, page_height: float) -> list[float]:
    scale = get_page_scale_896(page_width, page_height)
    return _round_bbox([value * scale for value in _coerce_bbox(bbox)])



def _build_page_metrics_map(page_metrics: list[dict[str, float | int]]) -> dict[int, dict[str, float | int]]:
    metrics_map: dict[int, dict[str, float | int]] = {}
    for metric in page_metrics:
        page_number = int(metric["page_number"])
        metrics_map[page_number] = metric
    return metrics_map



def _convert_annotation_bboxes(
    annotation: dict[str, Any],
    page_metrics: list[dict[str, float | int]],
    converter: Any,
) -> dict[str, Any]:
    converted = copy.deepcopy(annotation)
    metrics_map = _build_page_metrics_map(page_metrics)

    for page in converted.get("pages", []):
        page_number = int(page.get("page_number", 0))
        if page_number not in metrics_map:
            raise ValueError(f"Page {page_number} is not available in the PDF metrics.")

        metric = metrics_map[page_number]
        page_width = float(metric["page_width"])
        page_height = float(metric["page_height"])

        for element in page.get("elements", []):
            if "bbox" not in element:
                continue
            element["bbox"] = converter(element["bbox"], page_width, page_height)

    return converted



def convert_annotation_896_to_pdf(
    annotation: dict[str, Any],
    page_metrics: list[dict[str, float | int]],
) -> dict[str, Any]:
    return _convert_annotation_bboxes(annotation, page_metrics, bbox_896_to_pdf)



def convert_annotation_pdf_to_896(
    annotation: dict[str, Any],
    page_metrics: list[dict[str, float | int]],
) -> dict[str, Any]:
    return _convert_annotation_bboxes(annotation, page_metrics, bbox_pdf_to_896)
