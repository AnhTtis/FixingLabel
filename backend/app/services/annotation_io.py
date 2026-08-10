from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.core.config import SNAPSHOTS_DIR, load_label_config, resolve_labels_path
from app.schemas.annotation import AnnotationDocument, AnnotationPage
from app.services.pdf_render import get_page_count, get_page_size

LABEL_COLOR_FALLBACK = "#6b7280"


def _first_non_empty(*values, default=None):
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return default


def _normalize_bbox(raw_bbox) -> list[float]:
    if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) == 4:
        return [float(value) for value in raw_bbox]

    if isinstance(raw_bbox, dict):
        if all(key in raw_bbox for key in ("x0", "y0", "x1", "y1")):
            return [float(raw_bbox["x0"]), float(raw_bbox["y0"]), float(raw_bbox["x1"]), float(raw_bbox["y1"])]
        if all(key in raw_bbox for key in ("left", "top", "right", "bottom")):
            return [float(raw_bbox["left"]), float(raw_bbox["top"]), float(raw_bbox["right"]), float(raw_bbox["bottom"])]
        if all(key in raw_bbox for key in ("x", "y", "width", "height")):
            x = float(raw_bbox["x"])
            y = float(raw_bbox["y"])
            width = float(raw_bbox["width"])
            height = float(raw_bbox["height"])
            return [x, y, x + width, y + height]
        if all(key in raw_bbox for key in ("x", "y", "w", "h")):
            x = float(raw_bbox["x"])
            y = float(raw_bbox["y"])
            width = float(raw_bbox["w"])
            height = float(raw_bbox["h"])
            return [x, y, x + width, y + height]

    return [0.0, 0.0, 1.0, 1.0]


def _normalize_element(element: dict, page_number: int, element_index: int) -> dict:
    return {
        "id": str(_first_non_empty(element.get("id"), element.get("element_id"), default=f"p{page_number}_e{element_index}")),
        "label": str(_first_non_empty(element.get("label"), element.get("type"), default="para")),
        "bbox": _normalize_bbox(_first_non_empty(element.get("bbox"), element.get("box"), element.get("coordinates"), default=[0.0, 0.0, 1.0, 1.0])),
        "score": element.get("score"),
        "locked": bool(element.get("locked", False)),
        "hidden": bool(element.get("hidden", False)),
        "notes": str(element.get("notes", "")),
        "text": element.get("text") or element.get("content"),
        "reading_order": element.get("reading_order") if element.get("reading_order") is not None else element.get("order"),
    }


def normalize_annotation_payload(payload: dict) -> dict:
    pages = payload.get("pages") or payload.get("document_pages") or []
    normalized_pages = []

    for page_index, page in enumerate(pages, start=1):
        page_number = int(_first_non_empty(page.get("page_number"), page.get("index"), default=page_index))
        raw_elements = page.get("elements") or page.get("blocks") or page.get("items") or []
        elements = [_normalize_element(element, page_number, element_index) for element_index, element in enumerate(raw_elements, start=1)]

        normalized_pages.append(
            {
                "page_number": page_number,
                "width": float(page.get("width", 1.0)),
                "height": float(page.get("height", 1.0)),
                "elements": elements,
            }
        )

    meta = payload.get("meta") or {}
    return {
        "document_id": str(_first_non_empty(payload.get("document_id"), payload.get("doc_id"), payload.get("id"), default=f"imported-{uuid4().hex[:8]}")),
        "source_pdf": str(_first_non_empty(payload.get("source_pdf"), payload.get("source_file"), payload.get("pdf_path"), payload.get("file_path"), payload.get("path"), default="uploaded.pdf")),
        "meta": {
            "coord_space": meta.get("coord_space", "pdf"),
            "version": int(meta.get("version", 1)),
            "updated_at": meta.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        },
        "pages": normalized_pages,
    }


def load_annotation_from_text(annotation_text: str) -> AnnotationDocument:
    raw_payload = json.loads(annotation_text)
    normalized_payload = normalize_annotation_payload(raw_payload)
    return AnnotationDocument.model_validate(normalized_payload)


def sync_page_sizes(pdf_source: bytes | Path | str, annotation: AnnotationDocument) -> AnnotationDocument:
    expected_page_count = get_page_count(pdf_source)
    declared_page_numbers = {page.page_number for page in annotation.pages}

    for page_number in range(1, expected_page_count + 1):
        if page_number not in declared_page_numbers:
            width, height = get_page_size(pdf_source, page_number)
            annotation.pages.append(
                annotation.pages[0].model_copy(update={
                    "page_number": page_number,
                    "width": width,
                    "height": height,
                    "elements": []
                })
                if annotation.pages
                else AnnotationPage(
                    page_number=page_number,
                    width=width,
                    height=height,
                    elements=[]
                )
            )

    annotation.pages.sort(key=lambda page: page.page_number)

    for page in annotation.pages:
        width, height = get_page_size(pdf_source, page.page_number)
        page.width = width
        page.height = height

    return annotation


def prepare_annotation(pdf_name: str, pdf_source: bytes | Path | str, annotation_text: str) -> AnnotationDocument:
    annotation = load_annotation_from_text(annotation_text)
    annotation.source_pdf = pdf_name
    annotation.meta.updated_at = datetime.now(timezone.utc)
    if not annotation.document_id:
        annotation.document_id = f"session-{uuid4().hex[:8]}"
    return sync_page_sizes(pdf_source, annotation)


def _normalize_label_definition(label: dict, index: int) -> dict:
    label_id = str(_first_non_empty(label.get("id"), default=f"label_{index}"))
    return {
        "id": label_id,
        "name": str(_first_non_empty(label.get("name"), label.get("display_name"), default=label_id)),
        "color": str(_first_non_empty(label.get("color"), default=LABEL_COLOR_FALLBACK)),
        "shortcut": str(_first_non_empty(label.get("shortcut"), default="")),
    }



def normalize_label_definitions_payload(payload: dict | None) -> dict:
    raw_labels = (payload or {}).get("labels", [])
    normalized_labels = [_normalize_label_definition(label, index) for index, label in enumerate(raw_labels, start=1)]
    return {"labels": normalized_labels}



def _annotation_label_ids(annotation: AnnotationDocument | None) -> list[str]:
    if annotation is None:
        return []

    seen: set[str] = set()
    label_ids: list[str] = []
    for page in annotation.pages:
        for element in page.elements:
            if element.label not in seen:
                seen.add(element.label)
                label_ids.append(element.label)
    return label_ids



def load_label_definitions(
    annotation: AnnotationDocument | None = None,
    labels_path: str | Path | None = None,
    labels_payload: dict | None = None,
) -> dict:
    base_payload = labels_payload if labels_payload is not None else load_label_config(labels_path)
    normalized_labels = normalize_label_definitions_payload(base_payload).get("labels", [])
    known_by_id = {label["id"]: label for label in normalized_labels}

    for label_id in _annotation_label_ids(annotation):
        if label_id not in known_by_id:
            fallback_label = _normalize_label_definition({"id": label_id, "name": label_id}, len(normalized_labels) + 1)
            normalized_labels.append(fallback_label)
            known_by_id[label_id] = fallback_label

    return {"labels": normalized_labels}



def export_annotation_json(annotation: AnnotationDocument) -> str:
    return annotation.model_dump_json(indent=2)



def export_label_definitions_json(labels: dict) -> str:
    normalized_labels = normalize_label_definitions_payload(labels).get("labels", [])
    return json.dumps({"labels": normalized_labels}, indent=2, ensure_ascii=False)


def write_annotation_file(annotation: AnnotationDocument, output_path: str | Path) -> Path:
    path = Path(output_path).expanduser()
    path.write_text(export_annotation_json(annotation), encoding="utf-8")
    return path


def write_label_definitions_file(labels: dict, output_path: str | Path | None = None) -> Path:
    path = Path(output_path).expanduser() if output_path is not None else resolve_labels_path()
    path.write_text(export_label_definitions_json(labels), encoding="utf-8")
    return path


def write_snapshot(annotation: AnnotationDocument, output_dir: Path | None = None) -> Path:
    target_dir = output_dir or SNAPSHOTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = target_dir / f"{annotation.document_id or 'session'}-{timestamp}.annotations.json"
    path.write_text(export_annotation_json(annotation), encoding="utf-8")
    return path
