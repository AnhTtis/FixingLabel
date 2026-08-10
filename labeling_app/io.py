from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any


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



def build_document_record(
    *,
    pdf_bytes: bytes,
    pdf_name: str,
    annotation: dict[str, Any],
    json_name: str,
    json_path: str | None = None,
    source: str = "upload",
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
    }



def build_document_from_uploads(pdf_file: Any, json_file: Any) -> dict[str, Any]:
    pdf_bytes = pdf_file.getvalue()
    annotation = json.loads(json_file.getvalue().decode("utf-8"))
    return build_document_record(
        pdf_bytes=pdf_bytes,
        pdf_name=pdf_file.name,
        annotation=annotation,
        json_name=json_file.name,
        source="upload",
    )



def load_local_document(json_path: Path, pdf_path: Path | None = None) -> dict[str, Any]:
    resolved_json_path = json_path.resolve()
    candidate_pdf_path = pdf_path or resolved_json_path.with_suffix(".pdf")
    resolved_pdf_path = candidate_pdf_path.resolve()

    annotation = json.loads(resolved_json_path.read_text(encoding="utf-8"))
    pdf_bytes = resolved_pdf_path.read_bytes()

    return build_document_record(
        pdf_bytes=pdf_bytes,
        pdf_name=resolved_pdf_path.name,
        annotation=annotation,
        json_name=resolved_json_path.name,
        json_path=str(resolved_json_path),
        source="local",
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



def export_annotation_bytes(annotation: dict[str, Any]) -> bytes:
    return json.dumps(annotation, ensure_ascii=False, indent=2).encode("utf-8")



def save_annotation(annotation: dict[str, Any], destination: Path) -> None:
    destination.write_bytes(export_annotation_bytes(annotation))
