from __future__ import annotations

import hashlib
from typing import Any

import streamlit as st

DEFAULT_LABELS = [
    "text",
    "section_header",
    "list_item",
    "picture",
    "caption",
    "table",
]

BASE_LABEL_COLORS = {
    "text": "#2563eb",
    "section_header": "#7c3aed",
    "list_item": "#0f766e",
    "picture": "#ea580c",
    "caption": "#16a34a",
    "table": "#dc2626",
}

FALLBACK_COLORS = [
    "#0891b2",
    "#be123c",
    "#4f46e5",
    "#0284c7",
    "#65a30d",
    "#9333ea",
    "#c2410c",
]



def init_app_state() -> None:
    st.session_state.setdefault("document", None)
    st.session_state.setdefault("current_page", 1)
    st.session_state.setdefault("mode", "edit")
    st.session_state.setdefault("selected_element_id", None)
    st.session_state.setdefault("draft_bbox", None)
    st.session_state.setdefault("flash", None)
    st.session_state.setdefault("visible_labels", [])



def set_flash(kind: str, message: str) -> None:
    st.session_state.flash = {"kind": kind, "message": message}



def pop_flash() -> dict[str, str] | None:
    return st.session_state.pop("flash", None)



def get_document() -> dict[str, Any] | None:
    return st.session_state.get("document")



def load_document(document: dict[str, Any]) -> None:
    st.session_state.document = document
    st.session_state.current_page = 1
    st.session_state.mode = "edit"
    st.session_state.selected_element_id = None
    st.session_state.draft_bbox = None
    st.session_state.visible_labels = get_label_choices()



def mark_dirty() -> None:
    document = get_document()
    if document is not None:
        document["dirty"] = True



def mark_clean() -> None:
    document = get_document()
    if document is not None:
        document["dirty"] = False



def get_annotation() -> dict[str, Any] | None:
    document = get_document()
    if document is None:
        return None
    return document["annotation"]



def get_pages() -> list[dict[str, Any]]:
    annotation = get_annotation()
    if annotation is None:
        return []
    return annotation.setdefault("pages", [])



def get_page_count() -> int:
    annotation = get_annotation()
    if annotation is None:
        return 0
    pages = annotation.setdefault("pages", [])
    return max(int(annotation.get("total_pages") or len(pages)), len(pages))



def set_current_page(page_number: int) -> None:
    max_page = max(get_page_count(), 1)
    st.session_state.current_page = max(1, min(int(page_number), max_page))
    st.session_state.selected_element_id = None
    st.session_state.draft_bbox = None



def set_mode(mode: str) -> None:
    st.session_state.mode = mode
    st.session_state.draft_bbox = None
    if mode == "create":
        st.session_state.selected_element_id = None



def get_page_entry(page_number: int, *, create: bool = False) -> dict[str, Any] | None:
    pages = get_pages()
    for page in pages:
        if int(page.get("page_number", 0)) == int(page_number):
            page.setdefault("elements", [])
            return page

    if not create:
        return None

    new_page = {"page_number": int(page_number), "elements": []}
    pages.append(new_page)
    pages.sort(key=lambda page: int(page.get("page_number", 0)))

    annotation = get_annotation()
    if annotation is not None:
        annotation["total_pages"] = max(int(annotation.get("total_pages") or 0), int(page_number), len(pages))

    return new_page



def make_element_id(page_number: int, element_index: int) -> str:
    return f"p{page_number}-e{element_index}"



def parse_element_id(element_id: str) -> tuple[int, int]:
    page_part, element_part = element_id.split("-")
    return int(page_part[1:]), int(element_part[1:])



def get_page_elements(page_number: int) -> list[dict[str, Any]]:
    page = get_page_entry(page_number)
    if page is None:
        return []
    return page.setdefault("elements", [])



def get_viewer_elements(page_number: int, visible_labels: list[str] | None = None) -> list[dict[str, Any]]:
    visible = set(visible_labels or [])
    boxes: list[dict[str, Any]] = []

    for element_index, element in enumerate(get_page_elements(page_number)):
        label = str(element.get("label", "text"))
        if visible and label not in visible:
            continue

        text_preview = str(element.get("text", "")).replace("\n", " ")[:120]
        boxes.append(
            {
                "id": make_element_id(page_number, element_index),
                "label": label,
                "bbox": [float(value) for value in element.get("bbox", [0, 0, 0, 0])],
                "text": text_preview,
            }
        )

    return boxes



def select_element(element_id: str | None) -> None:
    st.session_state.selected_element_id = element_id
    st.session_state.draft_bbox = None



def clear_selection() -> None:
    st.session_state.selected_element_id = None



def set_draft_bbox(bbox: list[float]) -> None:
    st.session_state.draft_bbox = [float(value) for value in bbox]
    st.session_state.selected_element_id = None



def clear_draft_bbox() -> None:
    st.session_state.draft_bbox = None



def get_selected_element() -> tuple[str, dict[str, Any], int, int] | None:
    element_id = st.session_state.get("selected_element_id")
    if not element_id:
        return None

    page_number, element_index = parse_element_id(element_id)
    page = get_page_entry(page_number)
    if page is None:
        return None

    elements = page.setdefault("elements", [])
    if not (0 <= element_index < len(elements)):
        return None

    return element_id, elements[element_index], page_number, element_index



def delete_selected_element() -> None:
    selected = get_selected_element()
    if selected is None:
        return

    _, _, page_number, element_index = selected
    elements = get_page_elements(page_number)
    elements.pop(element_index)
    clear_selection()
    mark_dirty()



def normalize_bbox(bbox: list[float], page_width: float, page_height: float) -> list[float]:
    x0, y0, x1, y1 = [float(value) for value in bbox]
    left, right = sorted((x0, x1))
    top, bottom = sorted((y0, y1))

    left = max(0.0, min(left, page_width))
    right = max(0.0, min(right, page_width))
    top = max(0.0, min(top, page_height))
    bottom = max(0.0, min(bottom, page_height))

    return [round(left, 2), round(top, 2), round(right, 2), round(bottom, 2)]



def update_element_bbox(
    element_id: str,
    bbox: list[float],
    page_width: float,
    page_height: float,
) -> None:
    page_number, element_index = parse_element_id(element_id)
    elements = get_page_elements(page_number)
    if not (0 <= element_index < len(elements)):
        return

    elements[element_index]["bbox"] = normalize_bbox(bbox, page_width, page_height)
    st.session_state.selected_element_id = element_id
    mark_dirty()



def update_selected_element(
    *,
    label: str,
    bbox: list[float],
    text: str,
    reading_order: int,
    figure_path: str,
    page_width: float,
    page_height: float,
) -> None:
    selected = get_selected_element()
    if selected is None:
        return

    _, element, _, _ = selected
    element["label"] = label.strip() or "text"
    element["bbox"] = normalize_bbox(bbox, page_width, page_height)
    element["text"] = text
    element["reading_order"] = int(reading_order)

    cleaned_figure_path = figure_path.strip()
    if cleaned_figure_path:
        element["figure_path"] = cleaned_figure_path
    else:
        element.pop("figure_path", None)

    mark_dirty()



def next_reading_order(page_number: int) -> int:
    reading_orders = [int(element.get("reading_order", 0)) for element in get_page_elements(page_number)]
    if not reading_orders:
        return 0
    return max(reading_orders) + 1



def add_element(
    *,
    page_number: int,
    label: str,
    bbox: list[float],
    text: str,
    reading_order: int,
    figure_path: str,
    page_width: float,
    page_height: float,
) -> str:
    page = get_page_entry(page_number, create=True)
    if page is None:
        raise ValueError("Page could not be created.")

    element = {
        "label": label.strip() or "text",
        "bbox": normalize_bbox(bbox, page_width, page_height),
        "text": text,
        "reading_order": int(reading_order),
    }

    cleaned_figure_path = figure_path.strip()
    if cleaned_figure_path:
        element["figure_path"] = cleaned_figure_path

    page.setdefault("elements", []).append(element)
    element_id = make_element_id(page_number, len(page["elements"]) - 1)

    mark_dirty()
    return element_id



def get_label_choices() -> list[str]:
    labels = set(DEFAULT_LABELS)
    for page in get_pages():
        for element in page.get("elements", []):
            label = str(element.get("label", "")).strip()
            if label:
                labels.add(label)
    return sorted(labels)



def get_label_colors() -> dict[str, str]:
    colors = dict(BASE_LABEL_COLORS)

    for label in get_label_choices():
        if label in colors:
            continue
        digest = hashlib.sha256(label.encode("utf-8")).digest()[0]
        colors[label] = FALLBACK_COLORS[digest % len(FALLBACK_COLORS)]

    return colors
