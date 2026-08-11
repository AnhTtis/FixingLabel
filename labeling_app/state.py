from __future__ import annotations

import copy
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

HISTORY_LIMIT = 100
MIN_VIEWER_ZOOM = 1.0
MAX_VIEWER_ZOOM = 3.0
VIEWER_ZOOM_STEP = 0.25



def init_app_state() -> None:
    st.session_state.setdefault("document", None)
    st.session_state.setdefault("current_page", 1)
    st.session_state.setdefault("mode", "edit")
    st.session_state.setdefault("selected_element_id", None)
    st.session_state.setdefault("draft_bbox", None)
    st.session_state.setdefault("flash", None)
    st.session_state.setdefault("viewer_zoom", 1.0)
    st.session_state.setdefault("undo_stack", [])
    st.session_state.setdefault("redo_stack", [])
    st.session_state.setdefault("annotation_revision", 0)



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
    st.session_state.viewer_zoom = 1.0
    st.session_state.undo_stack = []
    st.session_state.redo_stack = []
    st.session_state.annotation_revision = 0
    st.session_state["_derived_cache_state"] = {}
    st.session_state["_annotation_export_cache"] = {}



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



def get_annotation_revision() -> int:
    return int(st.session_state.get("annotation_revision", 0))



def _bump_annotation_revision() -> None:
    st.session_state.annotation_revision = get_annotation_revision() + 1



def _get_revision_cache() -> dict[object, Any]:
    document = get_document()
    cache_state = st.session_state.setdefault("_derived_cache_state", {})
    cache_key = ((document or {}).get("doc_id"), get_annotation_revision())

    if cache_state.get("key") != cache_key:
        cache_state.clear()
        cache_state["key"] = cache_key
        cache_state["values"] = {}

    return cache_state["values"]



def get_viewer_zoom() -> float:
    return float(st.session_state.get("viewer_zoom", 1.0))



def set_viewer_zoom(value: float) -> None:
    st.session_state.viewer_zoom = max(MIN_VIEWER_ZOOM, min(float(value), MAX_VIEWER_ZOOM))



def zoom_in_viewer() -> None:
    set_viewer_zoom(get_viewer_zoom() + VIEWER_ZOOM_STEP)



def zoom_out_viewer() -> None:
    set_viewer_zoom(get_viewer_zoom() - VIEWER_ZOOM_STEP)



def reset_viewer_zoom() -> None:
    set_viewer_zoom(1.0)



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



def get_viewer_elements(page_number: int) -> list[dict[str, Any]]:
    cache = _get_revision_cache()
    cache_key = ("viewer_elements", int(page_number))
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    boxes: list[dict[str, Any]] = []
    for element_index, element in enumerate(get_page_elements(page_number)):
        text_preview = str(element.get("text", "")).replace("\n", " ")[:120]
        boxes.append(
            {
                "id": make_element_id(page_number, element_index),
                "label": str(element.get("label", "text")),
                "bbox": [float(value) for value in element.get("bbox", [0, 0, 0, 0])],
                "text": text_preview,
            }
        )

    cache[cache_key] = boxes
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

    selected_id, _, page_number, element_index = selected
    before_elements = snapshot_page_elements(page_number)
    after_elements = copy.deepcopy(before_elements)
    after_elements.pop(element_index)

    elements = get_page_elements(page_number)
    elements.pop(element_index)
    clear_selection()
    _push_history_entry(
        page_number=page_number,
        before_elements=before_elements,
        after_elements=after_elements,
        selected_before=selected_id,
        selected_after=None,
    )
    _bump_annotation_revision()
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



def snapshot_page_elements(page_number: int) -> list[dict[str, Any]]:
    return copy.deepcopy(get_page_elements(page_number))



def _set_page_elements(page_number: int, elements: list[dict[str, Any]]) -> None:
    page = get_page_entry(page_number, create=True)
    if page is None:
        raise ValueError("Page could not be created.")
    page["elements"] = copy.deepcopy(elements)



def _push_history_entry(
    *,
    page_number: int,
    before_elements: list[dict[str, Any]],
    after_elements: list[dict[str, Any]],
    selected_before: str | None,
    selected_after: str | None,
) -> None:
    if before_elements == after_elements:
        return

    entry = {
        "kind": "page_snapshot",
        "page_number": int(page_number),
        "before_elements": before_elements,
        "after_elements": after_elements,
        "selected_before": selected_before,
        "selected_after": selected_after,
    }

    undo_stack = list(st.session_state.get("undo_stack", []))
    undo_stack.append(entry)
    if len(undo_stack) > HISTORY_LIMIT:
        undo_stack = undo_stack[-HISTORY_LIMIT:]

    st.session_state.undo_stack = undo_stack
    st.session_state.redo_stack = []



def _push_bbox_history_entry(
    *,
    page_number: int,
    element_index: int,
    before_bbox: list[float],
    after_bbox: list[float],
    selected_before: str | None,
    selected_after: str | None,
) -> None:
    if before_bbox == after_bbox:
        return

    entry = {
        "kind": "bbox_update",
        "page_number": int(page_number),
        "element_index": int(element_index),
        "before_bbox": list(before_bbox),
        "after_bbox": list(after_bbox),
        "selected_before": selected_before,
        "selected_after": selected_after,
    }

    undo_stack = list(st.session_state.get("undo_stack", []))
    undo_stack.append(entry)
    if len(undo_stack) > HISTORY_LIMIT:
        undo_stack = undo_stack[-HISTORY_LIMIT:]

    st.session_state.undo_stack = undo_stack
    st.session_state.redo_stack = []



def can_undo() -> bool:
    return bool(st.session_state.get("undo_stack"))



def can_redo() -> bool:
    return bool(st.session_state.get("redo_stack"))



def _restore_selection(selected_id: str | None) -> None:
    if not selected_id:
        clear_selection()
        return

    page_number, element_index = parse_element_id(selected_id)
    elements = get_page_elements(page_number)
    if 0 <= element_index < len(elements):
        st.session_state.selected_element_id = selected_id
    else:
        clear_selection()



def _apply_bbox_history_entry(entry: dict[str, Any], bbox_field: str) -> bool:
    page_number = int(entry["page_number"])
    element_index = int(entry["element_index"])
    elements = get_page_elements(page_number)
    if not (0 <= element_index < len(elements)):
        return False

    elements[element_index]["bbox"] = [float(value) for value in entry[bbox_field]]
    return True



def undo_last_action() -> bool:
    undo_stack = list(st.session_state.get("undo_stack", []))
    if not undo_stack:
        return False

    entry = undo_stack.pop()

    if entry.get("kind") == "bbox_update":
        if not _apply_bbox_history_entry(entry, "before_bbox"):
            return False
    else:
        _set_page_elements(entry["page_number"], entry["before_elements"])

    st.session_state.undo_stack = undo_stack
    st.session_state.current_page = int(entry["page_number"])
    st.session_state.mode = "edit"
    clear_draft_bbox()
    _restore_selection(entry.get("selected_before"))

    redo_stack = list(st.session_state.get("redo_stack", []))
    redo_stack.append(entry)
    st.session_state.redo_stack = redo_stack[-HISTORY_LIMIT:]
    _bump_annotation_revision()
    mark_dirty()
    return True



def redo_last_action() -> bool:
    redo_stack = list(st.session_state.get("redo_stack", []))
    if not redo_stack:
        return False

    entry = redo_stack.pop()

    if entry.get("kind") == "bbox_update":
        if not _apply_bbox_history_entry(entry, "after_bbox"):
            return False
    else:
        _set_page_elements(entry["page_number"], entry["after_elements"])

    st.session_state.redo_stack = redo_stack
    st.session_state.current_page = int(entry["page_number"])
    st.session_state.mode = "edit"
    clear_draft_bbox()
    _restore_selection(entry.get("selected_after"))

    undo_stack = list(st.session_state.get("undo_stack", []))
    undo_stack.append(entry)
    st.session_state.undo_stack = undo_stack[-HISTORY_LIMIT:]
    _bump_annotation_revision()
    mark_dirty()
    return True



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

    normalized_bbox = normalize_bbox(bbox, page_width, page_height)
    current_bbox = normalize_bbox(elements[element_index].get("bbox", [0, 0, 0, 0]), page_width, page_height)
    if current_bbox == normalized_bbox:
        st.session_state.selected_element_id = element_id
        return

    selected_before = st.session_state.get("selected_element_id")
    elements[element_index]["bbox"] = normalized_bbox
    st.session_state.selected_element_id = element_id

    _push_bbox_history_entry(
        page_number=page_number,
        element_index=element_index,
        before_bbox=current_bbox,
        after_bbox=normalized_bbox,
        selected_before=selected_before,
        selected_after=element_id,
    )
    _bump_annotation_revision()
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

    selected_id, element, page_number, element_index = selected
    before_elements = snapshot_page_elements(page_number)
    selected_before = st.session_state.get("selected_element_id")

    updated_element = copy.deepcopy(before_elements[element_index])
    updated_element["label"] = label.strip() or "text"
    updated_element["bbox"] = normalize_bbox(bbox, page_width, page_height)
    updated_element["text"] = text
    updated_element["reading_order"] = int(reading_order)

    cleaned_figure_path = figure_path.strip()
    if cleaned_figure_path:
        updated_element["figure_path"] = cleaned_figure_path
    else:
        updated_element.pop("figure_path", None)

    if before_elements[element_index] == updated_element:
        st.session_state.selected_element_id = selected_id
        return

    after_elements = copy.deepcopy(before_elements)
    after_elements[element_index] = updated_element

    element.clear()
    element.update(copy.deepcopy(updated_element))

    _push_history_entry(
        page_number=page_number,
        before_elements=before_elements,
        after_elements=after_elements,
        selected_before=selected_before,
        selected_after=selected_id,
    )
    _bump_annotation_revision()
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
    before_elements = snapshot_page_elements(page_number)
    selected_before = st.session_state.get("selected_element_id")

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
    after_elements = copy.deepcopy(before_elements)
    after_elements.append(copy.deepcopy(element))

    _push_history_entry(
        page_number=page_number,
        before_elements=before_elements,
        after_elements=after_elements,
        selected_before=selected_before,
        selected_after=element_id,
    )
    _bump_annotation_revision()
    mark_dirty()
    return element_id



def get_label_choices() -> list[str]:
    cache = _get_revision_cache()
    cached = cache.get("label_choices")
    if cached is not None:
        return cached

    labels = set(DEFAULT_LABELS)
    for page in get_pages():
        for element in page.get("elements", []):
            label = str(element.get("label", "")).strip()
            if label:
                labels.add(label)

    choices = sorted(labels)
    cache["label_choices"] = choices
    return choices



def get_label_colors() -> dict[str, str]:
    cache = _get_revision_cache()
    cached = cache.get("label_colors")
    if cached is not None:
        return cached

    colors = dict(BASE_LABEL_COLORS)
    for label in get_label_choices():
        if label in colors:
            continue
        digest = hashlib.sha256(label.encode("utf-8")).digest()[0]
        colors[label] = FALLBACK_COLORS[digest % len(FALLBACK_COLORS)]

    cache["label_colors"] = colors
    return colors



def get_total_element_count() -> int:
    cache = _get_revision_cache()
    cached = cache.get("total_element_count")
    if cached is not None:
        return cached

    total = sum(len(page.get("elements", [])) for page in get_pages())
    cache["total_element_count"] = total
    return total
