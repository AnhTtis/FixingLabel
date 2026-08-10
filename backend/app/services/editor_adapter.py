from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.schemas.annotation import AnnotationDocument, AnnotationElement, BBoxPatch, CreatePatch
from app.services.coord_transform import PageGeometry, image_to_pdf_bbox, pdf_to_image_bbox

MIN_DRAW_PIXELS = 8.0
LABEL_COLOR_FALLBACK = "#6b7280"


def current_page(annotation: AnnotationDocument, page_number: int):
    for page in annotation.pages:
        if page.page_number == page_number:
            return page
    raise ValueError(f"Page {page_number} does not exist")



def page_option_label(page: Any) -> str:
    return f"Page {page.page_number} · {len(page.elements)} box(es) · {int(page.width)}×{int(page.height)}"



def page_label_count(page: Any) -> int:
    return len({element.label for element in page.elements})



def label_lookup(labels_payload: dict | None) -> dict[str, dict[str, str]]:
    labels = (labels_payload or {"labels": []}).get("labels", [])
    return {str(label["id"]): label for label in labels}



def label_display_name(labels_payload: dict | None, label_id: str) -> str:
    return label_lookup(labels_payload).get(label_id, {}).get("name", label_id)



def label_display_option(labels_payload: dict | None, label_id: str) -> str:
    label = label_lookup(labels_payload).get(label_id, {})
    shortcut = label.get("shortcut") or "-"
    return f"{label.get('name', label_id)} ({shortcut})"



def box_option_label(page: Any, labels_payload: dict | None, element_id: str) -> str:
    if not element_id:
        return "No selection"

    element = next((item for item in page.elements if item.id == element_id), None)
    if element is None:
        return element_id
    return f"{element_id} · {label_display_name(labels_payload, element.label)}"



def build_page_geometry(page: Any, image_width: int, image_height: int) -> PageGeometry:
    return PageGeometry(
        pdf_width=page.width,
        pdf_height=page.height,
        image_width=image_width,
        image_height=image_height,
    )



def build_canvas_boxes(page: Any, geometry: PageGeometry, labels_payload: dict | None) -> list[dict[str, Any]]:
    labels_by_id = label_lookup(labels_payload)
    boxes: list[dict[str, Any]] = []
    for element in page.elements:
        x0, y0, x1, y1 = pdf_to_image_bbox(list(element.bbox), geometry)
        label = labels_by_id.get(element.label, {})
        boxes.append(
            {
                "id": element.id,
                "label": element.label,
                "label_name": label.get("name", element.label),
                "color": label.get("color", LABEL_COLOR_FALLBACK),
                "left": round(x0, 2),
                "top": round(y0, 2),
                "width": round(max(1.0, x1 - x0), 2),
                "height": round(max(1.0, y1 - y0), 2),
            }
        )
    return boxes



def canvas_box_to_pdf_bbox(box: dict[str, Any], geometry: PageGeometry) -> list[float]:
    left = float(box.get("left", 0.0))
    top = float(box.get("top", 0.0))
    width = float(box.get("width", 0.0))
    height = float(box.get("height", 0.0))
    image_bbox = [left, top, left + width, top + height]
    pdf_bbox = image_to_pdf_bbox(image_bbox, geometry)
    return [round(value, 2) for value in pdf_bbox]



def canvas_payload_to_patch_operations(
    page: Any,
    geometry: PageGeometry,
    payload: list[dict[str, Any]] | None,
    labels_payload: dict | None,
) -> tuple[list[Any], list[str], list[str]]:
    if not payload:
        return [], [], []

    existing_by_id = {element.id: element for element in page.elements}
    operations: list[Any] = []
    created_ids: list[str] = []
    seen_existing_ids: set[str] = set()
    labels = (labels_payload or {"labels": []}).get("labels", [])
    default_label = labels[0]["id"] if labels else "unlabeled"

    for box in payload:
        bbox = canvas_box_to_pdf_bbox(box, geometry)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        if width <= 0 or height <= 0:
            continue

        image_width = float(box.get("width", 0.0))
        image_height = float(box.get("height", 0.0))
        if image_width < MIN_DRAW_PIXELS or image_height < MIN_DRAW_PIXELS:
            continue

        element_id = str(box.get("id") or "")
        if element_id and element_id in existing_by_id:
            seen_existing_ids.add(element_id)
            current_bbox = [round(value, 2) for value in existing_by_id[element_id].bbox]
            if current_bbox != bbox:
                operations.append(BBoxPatch(op="update_bbox", page=page.page_number, element_id=element_id, bbox=bbox))
            continue

        new_id = f"p{page.page_number}_{uuid4().hex[:8]}"
        operations.append(
            CreatePatch(
                op="create_element",
                page=page.page_number,
                element=AnnotationElement(
                    id=new_id,
                    label=str(box.get("label") or default_label),
                    bbox=bbox,
                    locked=False,
                    hidden=False,
                    notes="",
                ),
            )
        )
        created_ids.append(new_id)

    missing_existing_ids = [element_id for element_id in existing_by_id if element_id not in seen_existing_ids]
    return operations, created_ids, missing_existing_ids
