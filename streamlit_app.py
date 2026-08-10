from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any
import json
import sys

import pandas as pd
import streamlit as st
from PIL import Image


def ensure_streamlit_drawable_canvas_compat() -> None:
    """Patch Streamlit internals expected by streamlit-drawable-canvas on newer Streamlit builds."""
    try:
        import streamlit.elements.image as st_image
        if hasattr(st_image, "image_to_url"):
            return
        from streamlit.elements.lib.image_utils import image_to_url as raw_image_to_url
        from streamlit.elements.lib.layout_utils import create_layout_config
    except Exception:
        return

    def _compat_image_to_url(image, width, clamp, channels, output_format, image_id):
        layout_config = create_layout_config(width=width, allow_content_width=True)
        return raw_image_to_url(image, layout_config, clamp, channels, output_format, image_id)

    st_image.image_to_url = _compat_image_to_url


ensure_streamlit_drawable_canvas_compat()
import streamlit_drawable_canvas as drawable_canvas_module

PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import resolve_labels_path  # noqa: E402
from app.schemas.annotation import AnnotationDocument, BBoxPatch, DeletePatch, LabelPatch  # noqa: E402
from app.services.annotation_io import (  # noqa: E402
    export_annotation_json,
    export_label_definitions_json,
    load_label_definitions,
    prepare_annotation,
    write_annotation_file,
    write_label_definitions_file,
)
from app.services.editor_adapter import (  # noqa: E402
    box_option_label,
    build_canvas_boxes,
    build_canvas_initial_drawing,
    build_page_geometry,
    canvas_box_to_pdf_bbox,
    canvas_json_to_payload,
    canvas_payload_to_patch_operations,
    current_page,
    label_display_name,
    label_display_option,
    label_lookup,
    page_label_count,
    page_option_label,
    rgba_from_hex,
)
from app.services.patch_apply import PatchApplyError, apply_patches  # noqa: E402
from app.services.pdf_render import render_page_png  # noqa: E402

BASE_RENDER_SCALE = 1.5
STATE_KEY = "fixinglabel_state"
UPLOAD_MODE = "Upload files (web)"
PATH_MODE = "Local file paths"
CANVAS_SELECT_MODE = "Select / resize"
CANVAS_DRAW_MODE = "Draw new boxes"

st.set_page_config(page_title="FixingLabel Streamlit", layout="wide")



def empty_state() -> dict[str, Any]:
    return {
        "annotation": None,
        "labels": {"labels": []},
        "pdf_source": None,
        "pdf_name": "",
        "annotation_path": "",
        "annotation_name": "",
        "labels_path": "",
        "labels_name": "labels.json",
        "persist_to_disk": False,
        "source_mode": UPLOAD_MODE,
        "current_page": 1,
        "selected_element_id": "",
        "zoom": 1.0,
        "canvas_mode": CANVAS_SELECT_MODE,
        "new_box_label": "",
        "canvas_drafts": {},
        "last_error": None,
        "last_warning": None,
        "last_success": None,
    }



def state() -> dict[str, Any]:
    if STATE_KEY not in st.session_state:
        st.session_state[STATE_KEY] = empty_state()
    return st.session_state[STATE_KEY]



def initialize_inputs() -> None:
    default_labels_path = str(resolve_labels_path())
    st.session_state.setdefault("source_mode_input", UPLOAD_MODE)
    st.session_state.setdefault("pdf_path_input", "")
    st.session_state.setdefault("annotation_path_input", "")
    st.session_state.setdefault("labels_path_input", default_labels_path)



def reset_editor() -> None:
    st.session_state[STATE_KEY] = empty_state()



def set_success(message: str) -> None:
    current = state()
    current["last_success"] = message
    current["last_error"] = None



def set_warning(message: str | None) -> None:
    current = state()
    current["last_warning"] = message



def set_error(message: str) -> None:
    current = state()
    current["last_error"] = message
    current["last_success"] = None



def clear_messages() -> None:
    current = state()
    current["last_error"] = None
    current["last_warning"] = None
    current["last_success"] = None



@st.cache_data(show_spinner=False, max_entries=32)
def render_page_png_cached(pdf_source: bytes | str | Path, page_number: int, zoom: float) -> bytes:
    return render_page_png(pdf_source, page_number, scale=BASE_RENDER_SCALE * float(zoom))



def render_page_image(pdf_source: bytes | str | Path, page_number: int, zoom: float) -> Image.Image:
    png_bytes = render_page_png_cached(pdf_source, page_number, float(zoom))
    image = Image.open(BytesIO(png_bytes)).convert("RGBA")
    image.load()
    return image



def image_to_data_url(image: Image.Image, output_format: str = "PNG") -> str:
    buffer = BytesIO()
    image.save(buffer, format=output_format)
    encoded = drawable_canvas_module.base64.b64encode(buffer.getvalue()).decode("ascii")
    media_type = f"image/{output_format.lower()}"
    return f"data:{media_type};base64,{encoded}"



def stable_st_canvas(
    *,
    fill_color: str,
    stroke_width: int,
    stroke_color: str,
    background_color: str = "",
    background_image: Image.Image | None = None,
    update_streamlit: bool = True,
    height: int = 400,
    width: int = 600,
    drawing_mode: str = "freedraw",
    initial_drawing: dict[str, Any] | None = None,
    display_toolbar: bool = True,
    point_display_radius: int = 3,
    key: str | None = None,
):
    background_image_url = None
    if background_image is not None:
        background_image = drawable_canvas_module._resize_img(background_image, height, width)
        background_image_url = image_to_data_url(background_image)
        background_color = ""

    drawing = {"version": "4.4.0"} if initial_drawing is None else dict(initial_drawing)
    drawing["background"] = background_color

    component_value = drawable_canvas_module._component_func(
        fillColor=fill_color,
        strokeWidth=stroke_width,
        strokeColor=stroke_color,
        backgroundColor=background_color,
        backgroundImageURL=background_image_url,
        realtimeUpdateStreamlit=update_streamlit and (drawing_mode != "polygon"),
        canvasHeight=height,
        canvasWidth=width,
        drawingMode=drawing_mode,
        initialDrawing=drawing,
        displayToolbar=display_toolbar,
        displayRadius=point_display_radius,
        key=key,
        default=None,
    )
    if component_value is None:
        return drawable_canvas_module.CanvasResult()

    return drawable_canvas_module.CanvasResult(
        drawable_canvas_module.np.asarray(drawable_canvas_module._data_url_to_image(component_value["data"])),
        component_value["raw"],
    )



def fit_canvas_image(image: Image.Image, max_width: int = 900) -> Image.Image:
    if image.width <= max_width:
        return image
    scale = max_width / float(image.width)
    resized_height = max(1, int(round(image.height * scale)))
    return image.resize((max_width, resized_height), Image.Resampling.LANCZOS)



def clear_canvas_drafts(editor_state: dict[str, Any]) -> None:
    editor_state["canvas_drafts"] = {}



def canvas_draft_key(document_id: str, page_number: int, zoom: float, version: int) -> str:
    return f"{document_id}:{page_number}:{int(float(zoom) * 100)}:{version}"



def valid_canvas_json(canvas_json: dict[str, Any] | None) -> dict[str, Any] | None:
    if isinstance(canvas_json, dict) and isinstance(canvas_json.get("objects"), list):
        return canvas_json
    return None



def select_live_canvas_box(
    editor_state: dict[str, Any],
    payload: list[dict[str, Any]],
    existing_boxes: list[dict[str, Any]],
) -> dict[str, Any] | None:
    selected_id = str(editor_state.get("selected_element_id") or "")
    if selected_id:
        for box in payload:
            if str(box.get("id") or "") == selected_id:
                return box

    changed_existing = [
        box for box in payload
        if box.get("id") and any(
            str(existing.get("id") or "") == str(box.get("id") or "") and canvas_box_changed(box, existing)
            for existing in existing_boxes
        )
    ]
    if len(changed_existing) == 1:
        return changed_existing[0]

    draft_boxes = [box for box in payload if not box.get("id")]
    if draft_boxes:
        return draft_boxes[-1]
    return None



def selected_element(editor_state: dict[str, Any]):
    annotation: AnnotationDocument | None = editor_state.get("annotation")
    selected_id = editor_state.get("selected_element_id") or ""
    if annotation is None or not selected_id:
        return None
    page = current_page(annotation, int(editor_state["current_page"]))
    return next((element for element in page.elements if element.id == selected_id), None)



def ensure_valid_selection(editor_state: dict[str, Any]) -> None:
    annotation: AnnotationDocument | None = editor_state.get("annotation")
    if annotation is None:
        editor_state["selected_element_id"] = ""
        return

    page = current_page(annotation, int(editor_state["current_page"]))
    valid_ids = {element.id for element in page.elements}
    if editor_state.get("selected_element_id") not in valid_ids:
        editor_state["selected_element_id"] = ""



def label_ids(editor_state: dict[str, Any]) -> list[str]:
    labels_payload = editor_state.get("labels") or {"labels": []}
    return [str(label["id"]) for label in labels_payload.get("labels", [])]



def annotation_output_name(editor_state: dict[str, Any]) -> str:
    if editor_state.get("annotation_path"):
        return Path(editor_state["annotation_path"]).name
    return editor_state.get("annotation_name") or "corrected.annotations.json"



def labels_output_name(editor_state: dict[str, Any]) -> str:
    if editor_state.get("labels_path"):
        return Path(editor_state["labels_path"]).name
    return editor_state.get("labels_name") or "labels.json"



def save_annotation(editor_state: dict[str, Any], annotation: AnnotationDocument) -> str:
    if editor_state.get("persist_to_disk") and editor_state.get("annotation_path"):
        write_annotation_file(annotation, editor_state["annotation_path"])
        return f"Wrote changes to {annotation_output_name(editor_state)}."
    return f"Saved changes in this session. Download {annotation_output_name(editor_state)} to keep them."



def save_labels(editor_state: dict[str, Any], labels_payload: dict[str, Any]) -> str:
    if editor_state.get("persist_to_disk") and editor_state.get("labels_path"):
        write_label_definitions_file(labels_payload, editor_state["labels_path"])
        return f"Wrote label names to {labels_output_name(editor_state)}."
    return f"Saved label names in this session. Download {labels_output_name(editor_state)} to keep them."



def default_labels_name() -> str:
    return resolve_labels_path().name



def load_document(pdf_path_value: str, annotation_path_value: str, labels_path_value: str) -> None:
    editor_state = state()
    clear_messages()

    pdf_path = Path(pdf_path_value).expanduser()
    annotation_path = Path(annotation_path_value).expanduser()
    labels_path = resolve_labels_path(labels_path_value.strip() or None)

    if not pdf_path.exists():
        set_error(f"PDF path does not exist: {pdf_path}")
        return
    if not annotation_path.exists():
        set_error(f"Annotation JSON path does not exist: {annotation_path}")
        return

    try:
        annotation = prepare_annotation(
            pdf_name=pdf_path.name,
            pdf_source=pdf_path,
            annotation_text=annotation_path.read_text(encoding="utf-8"),
        )
        labels = load_label_definitions(annotation, labels_path=labels_path)
    except Exception as error:  # noqa: BLE001
        set_error(str(error))
        return

    editor_state.update(
        {
            "annotation": annotation,
            "labels": labels,
            "pdf_source": str(pdf_path),
            "pdf_name": pdf_path.name,
            "annotation_path": str(annotation_path),
            "annotation_name": annotation_path.name,
            "labels_path": str(labels_path),
            "labels_name": labels_path.name,
            "persist_to_disk": True,
            "source_mode": PATH_MODE,
            "current_page": 1,
            "selected_element_id": "",
            "zoom": 1.0,
            "canvas_mode": CANVAS_SELECT_MODE,
            "new_box_label": "",
            "canvas_drafts": {},
            "last_error": None,
            "last_warning": None,
            "last_success": f"Loaded {pdf_path.name} and {annotation_path.name}.",
        }
    )
    available_labels = label_ids(editor_state)
    editor_state["new_box_label"] = available_labels[0] if available_labels else ""
    st.session_state["labels_path_input"] = str(labels_path)



def load_uploaded_document(uploaded_pdf: Any, uploaded_annotation: Any, uploaded_labels: Any) -> None:
    editor_state = state()
    clear_messages()

    if uploaded_pdf is None or uploaded_annotation is None:
        set_error("Upload both a PDF file and an annotation JSON file.")
        return

    try:
        pdf_bytes = uploaded_pdf.getvalue()
        annotation_text = uploaded_annotation.getvalue().decode("utf-8")
        labels_payload = None
        labels_name = default_labels_name()
        if uploaded_labels is not None:
            labels_payload = json.loads(uploaded_labels.getvalue().decode("utf-8"))
            labels_name = uploaded_labels.name

        annotation = prepare_annotation(
            pdf_name=uploaded_pdf.name,
            pdf_source=pdf_bytes,
            annotation_text=annotation_text,
        )
        labels = load_label_definitions(annotation, labels_payload=labels_payload) if labels_payload is not None else load_label_definitions(annotation)
    except Exception as error:  # noqa: BLE001
        set_error(str(error))
        return

    editor_state.update(
        {
            "annotation": annotation,
            "labels": labels,
            "pdf_source": pdf_bytes,
            "pdf_name": uploaded_pdf.name,
            "annotation_path": "",
            "annotation_name": uploaded_annotation.name,
            "labels_path": "",
            "labels_name": labels_name,
            "persist_to_disk": False,
            "source_mode": UPLOAD_MODE,
            "current_page": 1,
            "selected_element_id": "",
            "zoom": 1.0,
            "canvas_mode": CANVAS_SELECT_MODE,
            "new_box_label": "",
            "canvas_drafts": {},
            "last_error": None,
            "last_warning": None,
            "last_success": f"Loaded uploads {uploaded_pdf.name} and {uploaded_annotation.name}.",
        }
    )
    available_labels = label_ids(editor_state)
    editor_state["new_box_label"] = available_labels[0] if available_labels else ""



def apply_element_updates(selected_id: str, label_id: str, bbox: list[float]) -> None:
    editor_state = state()
    annotation: AnnotationDocument | None = editor_state.get("annotation")
    if annotation is None or not selected_id:
        return

    operations = []
    element = selected_element(editor_state)
    if element is None:
        set_error("Select a box before saving changes.")
        return

    rounded_bbox = [round(value, 2) for value in bbox]
    if element.label != label_id:
        operations.append(LabelPatch(op="update_label", page=int(editor_state["current_page"]), element_id=selected_id, label=label_id))
    if [round(value, 2) for value in element.bbox] != rounded_bbox:
        operations.append(BBoxPatch(op="update_bbox", page=int(editor_state["current_page"]), element_id=selected_id, bbox=rounded_bbox))

    if not operations:
        set_warning("No box changes to save.")
        return

    try:
        working_copy = annotation.model_copy(deep=True)
        updated = apply_patches(working_copy, operations)
        editor_state["annotation"] = updated
        clear_canvas_drafts(editor_state)
        editor_state["selected_element_id"] = selected_id
        editor_state["last_error"] = None
        editor_state["last_warning"] = None
        editor_state["last_success"] = f"Saved box {selected_id}. {save_annotation(editor_state, updated)}"
    except PatchApplyError as error:
        set_error(str(error))



def delete_selected_box(selected_id: str) -> None:
    editor_state = state()
    annotation: AnnotationDocument | None = editor_state.get("annotation")
    if annotation is None or not selected_id:
        return

    try:
        working_copy = annotation.model_copy(deep=True)
        updated = apply_patches(
            working_copy,
            [DeletePatch(op="delete_element", page=int(editor_state["current_page"]), element_id=selected_id)],
        )
        editor_state["annotation"] = updated
        clear_canvas_drafts(editor_state)
        editor_state["selected_element_id"] = ""
        editor_state["last_error"] = None
        editor_state["last_warning"] = None
        editor_state["last_success"] = f"Deleted box {selected_id}. {save_annotation(editor_state, updated)}"
    except PatchApplyError as error:
        set_error(str(error))



def save_label_names(edited_labels: pd.DataFrame) -> None:
    editor_state = state()
    updated_labels: list[dict[str, str]] = []
    for row in edited_labels.to_dict("records"):
        label_id = str(row.get("id", "")).strip()
        if not label_id:
            continue
        updated_labels.append(
            {
                "id": label_id,
                "name": str(row.get("name", "")).strip() or label_id,
                "shortcut": str(row.get("shortcut", "")).strip(),
                "color": str(row.get("color", "#6b7280")).strip() or "#6b7280",
            }
        )

    labels_payload = {"labels": updated_labels}
    try:
        message = save_labels(editor_state, labels_payload)
    except OSError as error:
        set_error(str(error))
        return

    editor_state["labels"] = labels_payload
    if editor_state.get("new_box_label") not in label_ids(editor_state):
        available_labels = label_ids(editor_state)
        editor_state["new_box_label"] = available_labels[0] if available_labels else ""
    editor_state["last_error"] = None
    editor_state["last_warning"] = None
    editor_state["last_success"] = message



def build_elements_dataframe(editor_state: dict[str, Any]) -> pd.DataFrame:
    annotation: AnnotationDocument | None = editor_state.get("annotation")
    if annotation is None:
        return pd.DataFrame(columns=["id", "label", "label_name", "bbox"])

    page = current_page(annotation, int(editor_state["current_page"]))
    rows = [
        {
            "id": element.id,
            "label": element.label,
            "label_name": label_display_name(editor_state.get("labels"), element.label),
            "bbox": ", ".join(f"{value:.2f}" for value in element.bbox),
        }
        for element in page.elements
    ]
    return pd.DataFrame(rows)



def build_labels_dataframe(editor_state: dict[str, Any]) -> pd.DataFrame:
    labels = (editor_state.get("labels") or {"labels": []}).get("labels", [])
    return pd.DataFrame(
        [
            {
                "id": str(label.get("id", "")),
                "name": str(label.get("name", label.get("id", ""))),
                "shortcut": str(label.get("shortcut", "")),
                "color": str(label.get("color", "#6b7280")),
            }
            for label in labels
        ]
    )



def canvas_box_changed(candidate: dict[str, Any], existing: dict[str, Any]) -> bool:
    return any(abs(float(candidate[key]) - float(existing[key])) > 0.01 for key in ("left", "top", "width", "height"))



def infer_canvas_selection_id(
    payload: list[dict[str, Any]],
    existing_boxes: list[dict[str, Any]],
    current_selected_id: str,
) -> str:
    existing_by_id = {str(box["id"]): box for box in existing_boxes if box.get("id")}
    changed_ids: list[str] = []

    for box in payload:
        element_id = str(box.get("id") or "")
        if not element_id:
            continue
        existing = existing_by_id.get(element_id)
        if existing is not None and canvas_box_changed(box, existing):
            changed_ids.append(element_id)

    if len(changed_ids) == 1:
        return changed_ids[0]
    if current_selected_id and current_selected_id in existing_by_id:
        return current_selected_id
    return ""



def apply_canvas_changes(
    canvas_json: dict[str, Any] | None,
    existing_boxes: list[dict[str, Any]],
    new_box_label: str,
    image_width: int,
    image_height: int,
) -> None:
    editor_state = state()
    annotation: AnnotationDocument | None = editor_state.get("annotation")
    if annotation is None:
        return

    page = current_page(annotation, int(editor_state["current_page"]))
    geometry = build_page_geometry(page, image_width, image_height)
    payload = canvas_json_to_payload(canvas_json, existing_boxes, new_box_label)
    operations, created_ids, missing_existing_ids = canvas_payload_to_patch_operations(
        page,
        geometry,
        payload,
        editor_state.get("labels"),
    )

    if not operations:
        if len(payload) < len(existing_boxes):
            set_warning("Canvas changes did not include every existing box. Boxes are not auto-deleted; use the delete action in the properties panel.")
        else:
            set_warning("No canvas changes to save.")
        return

    try:
        working_copy = annotation.model_copy(deep=True)
        updated = apply_patches(working_copy, operations)
        editor_state["annotation"] = updated
        clear_canvas_drafts(editor_state)
        updated_existing_ids = [operation.element_id for operation in operations if getattr(operation, "op", "") == "update_bbox"]
        if created_ids:
            editor_state["selected_element_id"] = created_ids[-1]
        elif len(updated_existing_ids) == 1:
            editor_state["selected_element_id"] = updated_existing_ids[0]
        editor_state["last_error"] = None
        editor_state["last_warning"] = None
        editor_state["last_success"] = f"Applied canvas changes. {save_annotation(editor_state, updated)}"
        if missing_existing_ids:
            editor_state["last_warning"] = (
                "Canvas changes do not automatically delete missing boxes. "
                "Use the delete action in the properties panel if needed."
            )
    except PatchApplyError as error:
        set_error(str(error))



def render_status(editor_state: dict[str, Any]) -> None:
    if editor_state.get("last_error"):
        st.error(editor_state["last_error"])
    elif editor_state.get("last_warning"):
        st.warning(editor_state["last_warning"])
    elif editor_state.get("last_success"):
        st.success(editor_state["last_success"])
    else:
        st.info("Ready.")



def render_loaded_document(editor_state: dict[str, Any]) -> None:
    annotation: AnnotationDocument = editor_state["annotation"]
    page_numbers = [page.page_number for page in annotation.pages]
    current_page_number = int(editor_state.get("current_page", 1))
    if current_page_number not in page_numbers:
        current_page_number = page_numbers[0]
        editor_state["current_page"] = current_page_number

    selected_page = st.selectbox(
        "Page",
        options=page_numbers,
        index=page_numbers.index(current_page_number),
        format_func=lambda page_number: page_option_label(current_page(annotation, page_number)),
    )
    if selected_page != editor_state["current_page"]:
        editor_state["current_page"] = selected_page
        editor_state["selected_element_id"] = ""

    zoom = st.slider("Zoom", min_value=0.5, max_value=2.5, value=float(editor_state.get("zoom", 1.0)), step=0.1)
    editor_state["zoom"] = zoom
    ensure_valid_selection(editor_state)

    page = current_page(annotation, int(editor_state["current_page"]))
    available_labels = label_ids(editor_state)
    if not editor_state.get("new_box_label") and available_labels:
        editor_state["new_box_label"] = available_labels[0]
    if editor_state.get("new_box_label") and editor_state["new_box_label"] not in available_labels:
        editor_state["new_box_label"] = available_labels[0] if available_labels else ""

    st.caption(
        f"{annotation.source_pdf} · page {page.page_number}/{len(annotation.pages)} · "
        f"{len(page.elements)} box(es) · {page_label_count(page)} label(s) · version {annotation.meta.version}"
    )

    controls_col, mode_col = st.columns([1.4, 1.0], gap="medium")
    with controls_col:
        new_box_label = st.selectbox(
            "New box label",
            options=available_labels,
            index=available_labels.index(editor_state["new_box_label"]) if available_labels else 0,
            format_func=lambda value: label_display_option(editor_state.get("labels"), value),
            disabled=not available_labels,
        ) if available_labels else ""
        editor_state["new_box_label"] = new_box_label
    with mode_col:
        editor_state["canvas_mode"] = st.radio(
            "Canvas mode",
            options=[CANVAS_SELECT_MODE, CANVAS_DRAW_MODE],
            index=0 if editor_state.get("canvas_mode") == CANVAS_SELECT_MODE else 1,
            horizontal=True,
        )
    drawing_mode = "transform" if editor_state.get("canvas_mode") == CANVAS_SELECT_MODE else "rect"
    stroke_color = label_lookup(editor_state.get("labels")).get(new_box_label, {}).get("color", "#2563eb")

    original_image = render_page_image(editor_state["pdf_source"], page.page_number, float(editor_state["zoom"]))
    image = fit_canvas_image(original_image)
    geometry = build_page_geometry(page, image.width, image.height)
    canvas_boxes = build_canvas_boxes(page, geometry, editor_state.get("labels"))

    draft_key = canvas_draft_key(annotation.document_id, page.page_number, float(editor_state["zoom"]), int(annotation.meta.version))
    canvas_drafts = editor_state.setdefault("canvas_drafts", {})
    initial_drawing = valid_canvas_json(canvas_drafts.get(draft_key)) or build_canvas_initial_drawing(canvas_boxes)
    canvas_key = f"canvas-{draft_key}"

    st.markdown(
        """
        <style>
        .fixinglabel-sticky-panel { position: sticky; top: 1rem; }
        .fixinglabel-panel-scroll { max-height: calc(100vh - 8rem); overflow-y: auto; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    canvas_col, details_col = st.columns([3.0, 1.2], gap="medium")

    with canvas_col:
        canvas_result = stable_st_canvas(
            fill_color=rgba_from_hex(stroke_color, 0.08),
            stroke_width=2,
            stroke_color=stroke_color,
            background_image=image,
            update_streamlit=True,
            height=image.height,
            width=image.width,
            drawing_mode=drawing_mode,
            initial_drawing=initial_drawing,
            display_toolbar=False,
            key=canvas_key,
        )

        live_canvas_json = valid_canvas_json(getattr(canvas_result, "json_data", None))
        if live_canvas_json is not None:
            canvas_drafts[draft_key] = live_canvas_json
        active_canvas_json = live_canvas_json or valid_canvas_json(canvas_drafts.get(draft_key)) or initial_drawing

        canvas_payload = canvas_json_to_payload(active_canvas_json, canvas_boxes, new_box_label)
        inferred_selected_id = infer_canvas_selection_id(
            canvas_payload,
            canvas_boxes,
            editor_state.get("selected_element_id") or "",
        )
        if inferred_selected_id and inferred_selected_id != editor_state.get("selected_element_id"):
            editor_state["selected_element_id"] = inferred_selected_id

        st.caption(
            "Click and interact directly on the PDF canvas. Resize or move a box to update the detail panel on the right; "
            "drawing a new box will also show its label and bbox there before you apply changes."
        )
        if st.button("Apply canvas changes", type="primary", width="stretch"):
            apply_canvas_changes(active_canvas_json, canvas_boxes, new_box_label, image.width, image.height)
            st.rerun()

        st.subheader("Boxes on this page")
        st.dataframe(build_elements_dataframe(editor_state), hide_index=True, width="stretch")

    live_selected_box = select_live_canvas_box(editor_state, canvas_payload, canvas_boxes)

    with details_col:
        st.markdown('<div class="fixinglabel-sticky-panel"><div class="fixinglabel-panel-scroll">', unsafe_allow_html=True)
        detail_panel = st.container(border=True)
        with detail_panel:
            st.subheader("Selected box")
            if live_selected_box is None:
                st.info("Click, move, resize, or draw a box on the PDF to inspect it here.")
            else:
                live_label_id = str(live_selected_box.get("label") or new_box_label)
                live_label_name = label_display_name(editor_state.get("labels"), live_label_id)
                live_pdf_bbox = canvas_box_to_pdf_bbox(live_selected_box, geometry)
                live_canvas_bbox = [
                    round(float(live_selected_box.get("left", 0.0)), 2),
                    round(float(live_selected_box.get("top", 0.0)), 2),
                    round(float(live_selected_box.get("left", 0.0)) + float(live_selected_box.get("width", 0.0)), 2),
                    round(float(live_selected_box.get("top", 0.0)) + float(live_selected_box.get("height", 0.0)), 2),
                ]
                element_id = str(live_selected_box.get("id") or "")

                st.markdown(f"**Label:** {live_label_name}")
                st.caption(f"Label ID: {live_label_id}")
                if element_id:
                    st.caption(f"Element ID: {element_id}")
                else:
                    st.caption("New box · unsaved until you apply canvas changes")

                st.markdown("**Current bbox (PDF space)**")
                st.code(json.dumps({"bbox": live_pdf_bbox}, ensure_ascii=False), language="json")
                st.markdown("**Current bbox (canvas space)**")
                st.code(json.dumps({"bbox": live_canvas_bbox}, ensure_ascii=False), language="json")

                if element_id:
                    current_label_ids = available_labels.copy()
                    if live_label_id not in current_label_ids:
                        current_label_ids.append(live_label_id)
                    current_label_ids = current_label_ids or [live_label_id]
                    current_label_index = current_label_ids.index(live_label_id)

                    with st.form("box_editor_form"):
                        label_id = st.selectbox(
                            "Label ID",
                            options=current_label_ids,
                            index=current_label_index,
                            format_func=lambda value: label_display_option(editor_state.get("labels"), value),
                        )
                        x0 = st.number_input("x0", value=float(live_pdf_bbox[0]), step=1.0, format="%.2f")
                        y0 = st.number_input("y0", value=float(live_pdf_bbox[1]), step=1.0, format="%.2f")
                        x1 = st.number_input("x1", value=float(live_pdf_bbox[2]), step=1.0, format="%.2f")
                        y1 = st.number_input("y1", value=float(live_pdf_bbox[3]), step=1.0, format="%.2f")
                        save_box = st.form_submit_button("Save box changes", type="primary")
                        remove_box = st.form_submit_button("Delete selected box")

                    if save_box:
                        apply_element_updates(element_id, label_id, [x0, y0, x1, y1])
                        st.rerun()
                    if remove_box:
                        delete_selected_box(element_id)
                        st.rerun()
                else:
                    st.info("This box is still a draft. Click Apply canvas changes to create it in the annotation JSON.")
        st.markdown('</div></div>', unsafe_allow_html=True)

    st.subheader("Label names")
    if editor_state.get("persist_to_disk"):
        st.caption("Edit display names and save them directly to the labels JSON file.")
    else:
        st.caption("Edit display names in this browser session, then download the labels JSON to keep them.")
    with st.form("label_names_form"):
        edited_labels = st.data_editor(
            build_labels_dataframe(editor_state),
            hide_index=True,
            width="stretch",
            disabled=["id"],
            column_config={
                "id": st.column_config.TextColumn("Label ID"),
                "name": st.column_config.TextColumn("Display name", required=True),
                "shortcut": st.column_config.TextColumn("Shortcut"),
                "color": st.column_config.TextColumn("Color"),
            },
            num_rows="fixed",
        )
        save_names = st.form_submit_button("Save label names", type="primary")

    if save_names:
        save_label_names(edited_labels)
        st.rerun()

    st.subheader("Downloads")
    st.download_button(
        "Download current annotation JSON",
        data=export_annotation_json(annotation),
        file_name=annotation_output_name(editor_state),
        mime="application/json",
        width="stretch",
    )
    st.download_button(
        "Download current labels JSON",
        data=export_label_definitions_json(editor_state.get("labels") or {"labels": []}),
        file_name=labels_output_name(editor_state),
        mime="application/json",
        width="stretch",
    )



def main() -> None:
    initialize_inputs()
    editor_state = state()

    st.title("FixingLabel · Streamlit")
    st.caption("Edit PDF labels in Streamlit with upload-based web mode and optional local path mode.")

    with st.sidebar:
        st.header("Document")
        source_mode = st.radio("Input mode", options=[UPLOAD_MODE, PATH_MODE], key="source_mode_input")

        if source_mode == UPLOAD_MODE:
            uploaded_pdf = st.file_uploader("PDF", type=["pdf"])
            uploaded_annotation = st.file_uploader("Annotation JSON", type=["json"])
            uploaded_labels = st.file_uploader("Labels JSON (optional)", type=["json"])
            load_clicked = st.button("Load uploaded files", type="primary", width="stretch")
            if load_clicked:
                load_uploaded_document(uploaded_pdf, uploaded_annotation, uploaded_labels)
                st.rerun()
            st.caption("Web deployment uses uploads and session state. Download the edited JSON files to keep your changes.")
        else:
            st.text_input("PDF path", key="pdf_path_input", placeholder="D:/path/to/document.pdf")
            st.text_input("Annotation JSON path", key="annotation_path_input", placeholder="D:/path/to/document.annotations.json")
            st.text_input("Labels JSON path", key="labels_path_input")
            load_clicked = st.button("Load files", type="primary", width="stretch")
            reload_clicked = st.button("Reload from disk", width="stretch")
            if load_clicked or reload_clicked:
                load_document(
                    st.session_state["pdf_path_input"],
                    st.session_state["annotation_path_input"],
                    st.session_state["labels_path_input"],
                )
                st.rerun()
            st.caption("Local path mode writes annotation and label edits back to disk immediately.")

        unload_clicked = st.button("Unload current document", width="stretch")
        if unload_clicked:
            reset_editor()
            clear_messages()
            st.rerun()

        if editor_state.get("annotation") is not None:
            st.markdown(f"**Source mode:** `{editor_state['source_mode']}`")
            st.markdown(f"**PDF:** `{editor_state['pdf_name']}`")
            st.markdown(f"**Annotation JSON:** `{annotation_output_name(editor_state)}`")
            st.markdown(f"**Labels JSON:** `{labels_output_name(editor_state)}`")
            if editor_state.get("persist_to_disk"):
                st.markdown(f"**Annotation path:** `{editor_state['annotation_path']}`")
                st.markdown(f"**Labels path:** `{editor_state['labels_path']}`")

    render_status(editor_state)

    if editor_state.get("annotation") is None:
        if st.session_state["source_mode_input"] == UPLOAD_MODE:
            st.info("Upload a PDF and annotation JSON in the sidebar to start editing.")
        else:
            st.info("Enter local file paths in the sidebar, then load the document to start editing.")
        return

    render_loaded_document(editor_state)


if __name__ == "__main__":
    main()
