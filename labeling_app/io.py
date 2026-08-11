from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from labeling_app.coordinates import (
    PDF_COORDINATE_SPACE,
    SCALED_896_COORDINATE_SPACE,
    TARGET_MAX_DIM,
    convert_annotation_896_to_pdf,
    convert_annotation_pdf_to_896,
)
from labeling_app.pdf_render import get_pdf_page_metrics

APP_METADATA_KEY = "_labeling_app"
DEFAULT_SOURCE_SPACE = SCALED_896_COORDINATE_SPACE
DEFAULT_EXPORT_SPACE = SCALED_896_COORDINATE_SPACE



def _document_hash(pdf_bytes: bytes, annotation: dict[str, Any]) -> str:
    payload = json.dumps(annotation, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(pdf_bytes)
    digest.update(payload)
    return digest.hexdigest()[:16]



def normalize_annotation(annotation: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(annotation)
    pages = normalized.setdefault("pages", [])
    normalized["total_pages"] = int(normalized.get("total_pages") or len(pages))

    for page_index, page in enumerate(pages, start=1):
        page.setdefault("page_number", page_index)
        page.setdefault("elements", [])
        for element_index, element in enumerate(page["elements"]):
            element.setdefault("label", "text")
            element.setdefault("bbox", [0.0, 0.0, 0.0, 0.0])
            element.setdefault("text", "")
            element.setdefault("reading_order", element_index)

    return normalized



def _detect_source_space(annotation: dict[str, Any]) -> str:
    metadata = annotation.get(APP_METADATA_KEY)
    if isinstance(metadata, dict):
        coordinate_space = metadata.get("coordinate_space")
        if coordinate_space in {PDF_COORDINATE_SPACE, SCALED_896_COORDINATE_SPACE}:
            return str(coordinate_space)
    return DEFAULT_SOURCE_SPACE



def _build_coord_meta(
    *,
    page_metrics: list[dict[str, float | int]],
    source_space: str,
    default_export_space: str,
) -> dict[str, Any]:
    return {
        "internal_space": PDF_COORDINATE_SPACE,
        "source_space": source_space,
        "default_export_space": default_export_space,
        "target_max_dim": TARGET_MAX_DIM,
        "padding_removed": True,
        "page_metrics": page_metrics,
    }



def _convert_annotation_to_internal_space(
    annotation: dict[str, Any],
    page_metrics: list[dict[str, float | int]],
    source_space: str,
) -> dict[str, Any]:
    normalized = normalize_annotation(annotation)
    if source_space == PDF_COORDINATE_SPACE:
        return normalized
    if source_space == SCALED_896_COORDINATE_SPACE:
        return convert_annotation_896_to_pdf(normalized, page_metrics)
    raise ValueError(f"Unsupported source coordinate space: {source_space}")



def build_document_record(
    *,
    pdf_bytes: bytes,
    pdf_name: str,
    annotation: dict[str, Any],
    page_metrics: list[dict[str, float | int]],
    json_name: str,
    json_path: str | None = None,
    source: str = "upload",
    source_space: str = DEFAULT_SOURCE_SPACE,
    default_export_space: str = DEFAULT_EXPORT_SPACE,
) -> dict[str, Any]:
    normalized = normalize_annotation(annotation)
    return {
        "doc_id": _document_hash(pdf_bytes, normalized),
        "source": source,
        "pdf_name": pdf_name,
        "pdf_bytes": pdf_bytes,
        "json_name": json_name,
        "json_path": json_path,
        "dirty": False,
        "annotation": normalized,
        "page_metrics": page_metrics,
        "coord_meta": _build_coord_meta(
            page_metrics=page_metrics,
            source_space=source_space,
            default_export_space=default_export_space,
        ),
    }



def _build_document_from_raw(
    *,
    pdf_bytes: bytes,
    pdf_name: str,
    annotation: dict[str, Any],
    json_name: str,
    json_path: str | None,
    source: str,
    source_space: str | None = None,
    default_export_space: str = DEFAULT_EXPORT_SPACE,
) -> dict[str, Any]:
    page_metrics = get_pdf_page_metrics(pdf_bytes)
    resolved_source_space = source_space or _detect_source_space(annotation)
    internal_annotation = _convert_annotation_to_internal_space(annotation, page_metrics, resolved_source_space)
    return build_document_record(
        pdf_bytes=pdf_bytes,
        pdf_name=pdf_name,
        annotation=internal_annotation,
        page_metrics=page_metrics,
        json_name=json_name,
        json_path=json_path,
        source=source,
        source_space=resolved_source_space,
        default_export_space=default_export_space,
    )



def build_document_from_uploads(
    pdf_file: Any,
    json_file: Any,
    *,
    source_space: str | None = None,
) -> dict[str, Any]:
    pdf_bytes = pdf_file.getvalue()
    annotation = json.loads(json_file.getvalue().decode("utf-8"))
    return _build_document_from_raw(
        pdf_bytes=pdf_bytes,
        pdf_name=pdf_file.name,
        annotation=annotation,
        json_name=json_file.name,
        json_path=None,
        source="upload",
        source_space=source_space,
    )



def load_local_document(
    json_path: Path,
    pdf_path: Path | None = None,
    *,
    source_space: str | None = None,
) -> dict[str, Any]:
    resolved_json_path = json_path.resolve()
    candidate_pdf_path = pdf_path or resolved_json_path.with_suffix(".pdf")
    resolved_pdf_path = candidate_pdf_path.resolve()

    annotation = json.loads(resolved_json_path.read_text(encoding="utf-8"))
    pdf_bytes = resolved_pdf_path.read_bytes()

    return _build_document_from_raw(
        pdf_bytes=pdf_bytes,
        pdf_name=resolved_pdf_path.name,
        annotation=annotation,
        json_name=resolved_json_path.name,
        json_path=str(resolved_json_path),
        source="local",
        source_space=source_space,
    )



def discover_local_pairs(base_dir: Path) -> list[dict[str, str]]:
    pairs: list[dict[str, str]] = []

    for json_path in sorted(base_dir.glob("*.json")):
        pdf_path = json_path.with_suffix(".pdf")
        if not pdf_path.exists():
            continue

        pairs.append(
            {
                "label": f"{json_path.name} + {pdf_path.name}",
                "json_path": str(json_path.resolve()),
                "pdf_path": str(pdf_path.resolve()),
            }
        )

    return pairs



def build_export_annotation(document: dict[str, Any], export_space: str | None = None) -> dict[str, Any]:
    annotation = normalize_annotation(document["annotation"])
    coord_meta = document.get("coord_meta") or {}
    resolved_export_space = export_space or coord_meta.get("default_export_space") or DEFAULT_EXPORT_SPACE
    page_metrics = document.get("page_metrics") or coord_meta.get("page_metrics") or []

    if resolved_export_space == PDF_COORDINATE_SPACE:
        exported = annotation
    elif resolved_export_space == SCALED_896_COORDINATE_SPACE:
        exported = convert_annotation_pdf_to_896(annotation, page_metrics)
    else:
        raise ValueError(f"Unsupported export coordinate space: {resolved_export_space}")

    metadata = exported.get(APP_METADATA_KEY)
    if not isinstance(metadata, dict):
        metadata = {}

    metadata.update(
        {
            "coordinate_space": resolved_export_space,
            "editor_space": PDF_COORDINATE_SPACE,
            "target_max_dim": TARGET_MAX_DIM,
            "padding_removed": True,
        }
    )
    exported[APP_METADATA_KEY] = metadata
    return exported



def export_annotation_bytes(document: dict[str, Any], export_space: str | None = None) -> bytes:
    annotation = build_export_annotation(document, export_space=export_space)
    return json.dumps(annotation, ensure_ascii=False, indent=2).encode("utf-8")



def save_annotation(document: dict[str, Any], destination: Path, export_space: str | None = None) -> None:
    destination.write_bytes(export_annotation_bytes(document, export_space=export_space))
