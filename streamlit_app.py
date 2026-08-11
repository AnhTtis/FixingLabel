from __future__ import annotations

import hashlib
import json
from pathlib import Path

import streamlit as st

from labeling_app.components.bbox_viewer import bbox_viewer
from labeling_app.io import (
    build_document_from_uploads,
    discover_local_pairs,
    export_annotation_bytes,
    load_local_document,
    save_annotation,
)
from labeling_app.pdf_render import clear_pdf_render_cache, get_pdf_page_count, render_page_as_data_uri
from labeling_app.state import (
    add_element,
    can_redo,
    can_undo,
    clear_draft_bbox,
    clear_selection,
    delete_selected_element,
    get_annotation,
    get_annotation_revision,
    get_document,
    get_label_choices,
    get_label_colors,
    get_page_count,
    get_page_elements,
    get_selected_element,
    get_total_element_count,
    get_viewer_elements,
    get_viewer_zoom,
    init_app_state,
    load_document,
    mark_clean,
    next_reading_order,
    pop_flash,
    redo_last_action,
    reset_viewer_zoom,
    select_element,
    set_current_page,
    set_draft_bbox,
    set_flash,
    set_mode,
    undo_last_action,
    unload_document,
    update_element_bbox,
    update_selected_element,
    zoom_in_viewer,
    zoom_out_viewer,
)

st.set_page_config(
    page_title="PDF label studio",
    page_icon="🏷️",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_app_state()



def make_widget_state_suffix(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()[:10]



def show_flash_message() -> None:
    flash = pop_flash()
    if not flash:
        return

    kind = flash.get("kind")
    message = flash.get("message", "")

    if kind == "success":
        st.success(message, icon=":material/check_circle:")
    elif kind == "warning":
        st.warning(message, icon=":material/warning:")
    else:
        st.info(message, icon=":material/info:")



def get_viewer_component_key(document: dict[str, object]) -> str:
    return f"bbox-viewer-{document['doc_id']}-{st.session_state.current_page}"



def get_cached_export_bytes() -> bytes:
    document = get_document()
    annotation = get_annotation()
    if document is None or annotation is None:
        return b""

    export_space = ((document.get("coord_meta") or {}).get("default_export_space") or "scaled_896_xyxy")
    cache = st.session_state.setdefault("_annotation_export_cache", {})
    cache_key = (document["doc_id"], get_annotation_revision(), export_space)
    if cache.get("key") != cache_key:
        cache["key"] = cache_key
        cache["value"] = export_annotation_bytes(document, export_space=export_space)

    return cache["value"]



def release_current_document_resources(*, clear_document: bool) -> None:
    clear_pdf_render_cache()
    st.session_state["_annotation_export_cache"] = {}
    st.session_state["_derived_cache_state"] = {}

    for state_key in list(st.session_state.keys()):
        if isinstance(state_key, str) and state_key.startswith("bbox-viewer-"):
            st.session_state.pop(state_key, None)

    if clear_document:
        st.session_state.pop("uploaded_pdf", None)
        st.session_state.pop("uploaded_json", None)
        unload_document()


if st.session_state.pop("_pending_document_unload", False):
    release_current_document_resources(clear_document=True)



def _read_component_field(component_key: str, field_name: str) -> object:
    component_state = st.session_state.get(component_key)
    if component_state is None:
        return None
    if isinstance(component_state, dict):
        return component_state.get(field_name)
    return getattr(component_state, field_name, None)



def apply_pending_viewer_events(component_key: str, page_width: float, page_height: float) -> None:
    selected = _read_component_field(component_key, "selected")
    if isinstance(selected, str):
        if selected == "__clear__":
            clear_selection()
        else:
            select_element(selected)

    draft_payload = _read_component_field(component_key, "draft_bbox")
    if isinstance(draft_payload, dict):
        bbox = draft_payload.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            set_draft_bbox([float(value) for value in bbox])

    bbox_changed = _read_component_field(component_key, "bbox_changed")
    if isinstance(bbox_changed, dict):
        element_id = bbox_changed.get("id")
        bbox = bbox_changed.get("bbox")
        if isinstance(element_id, str) and isinstance(bbox, list) and len(bbox) == 4:
            update_element_bbox(
                element_id,
                [float(value) for value in bbox],
                page_width,
                page_height,
            )



def render_local_loader() -> None:
    st.subheader("Sample local")
    st.caption("Dùng nhanh cặp `.pdf` + `.json` đang có sẵn trong repo.")

    local_pairs = discover_local_pairs(Path.cwd())
    if not local_pairs:
        st.caption("Không tìm thấy cặp file `.json` + `.pdf` cùng tên trong thư mục hiện tại.")
        return

    options = ["— Chọn sample local —", *[pair["label"] for pair in local_pairs]]
    selected_label = st.selectbox("Sample local", options=options, key="local_pair_selector")

    if st.button("Load sample local", use_container_width=True):
        if selected_label == options[0]:
            set_flash("warning", "Hãy chọn một sample local trước khi load.")
            st.rerun()

        pair = next(pair for pair in local_pairs if pair["label"] == selected_label)
        try:
            document = load_local_document(Path(pair["json_path"]), Path(pair["pdf_path"]))
        except Exception as error:  # pragma: no cover - UI feedback
            set_flash("warning", f"Không load được sample local: {error}")
            st.rerun()

        release_current_document_resources(clear_document=True)
        load_document(document)
        set_flash("success", f"Đã load {Path(pair['json_path']).name}.")
        st.rerun()



def render_upload_loader() -> None:
    st.subheader("Upload tài liệu")
    st.caption("Khi deploy, người dùng có thể tải PDF và JSON trực tiếp từ giao diện này.")

    uploaded_pdf = st.file_uploader("PDF", type=["pdf"], key="uploaded_pdf")
    uploaded_json = st.file_uploader("JSON", type=["json"], key="uploaded_json")

    if st.button("Load file upload", use_container_width=True):
        if uploaded_pdf is None or uploaded_json is None:
            set_flash("warning", "Hãy chọn cả file PDF và JSON.")
            st.rerun()

        try:
            document = build_document_from_uploads(uploaded_pdf, uploaded_json)
        except Exception as error:  # pragma: no cover - UI feedback
            set_flash("warning", f"Không đọc được file upload: {error}")
            st.rerun()

        release_current_document_resources(clear_document=True)
        load_document(document)
        set_flash("success", f"Đã load {uploaded_json.name} và {uploaded_pdf.name}.")
        st.rerun()



def render_document_controls(pdf_page_count: int) -> None:
    document = get_document()
    annotation = get_annotation()
    if document is None or annotation is None:
        return

    st.subheader("Điều khiển")

    mode = st.segmented_control(
        "Chế độ",
        options=["edit", "create"],
        format_func=lambda option: "Chỉnh label" if option == "edit" else "Tạo label mới",
        key="mode",
        width="stretch",
    )
    if mode not in {"edit", "create"}:
        set_mode("edit")
        st.rerun()

    with st.container(horizontal=True, horizontal_alignment="distribute"):
        if st.button("Trang trước", icon=":material/arrow_back:"):
            set_current_page(st.session_state.current_page - 1)
            st.rerun()
        if st.button("Trang sau", icon=":material/arrow_forward:"):
            set_current_page(min(st.session_state.current_page + 1, max(pdf_page_count, 1)))
            st.rerun()

    chosen_page = st.number_input(
        "Trang hiện tại",
        min_value=1,
        max_value=max(pdf_page_count, 1),
        value=int(st.session_state.current_page),
        step=1,
        help="Chọn trang muốn hiển thị và chỉnh label.",
    )
    if int(chosen_page) != int(st.session_state.current_page):
        set_current_page(int(chosen_page))
        st.rerun()

    st.subheader("Lưu kết quả")
    export_bytes = get_cached_export_bytes()
    suggested_name = document["json_name"].removesuffix(".json") + "_edited.json"
    st.download_button(
        "Tải JSON đã chỉnh",
        data=export_bytes,
        file_name=suggested_name,
        mime="application/json",
        use_container_width=True,
        icon=":material/download:",
    )
    st.caption(":material/swap_horiz: File xuất ra dùng bbox 896 xyxy theo đúng scale max-dim 896 của dataset.")

    if document.get("json_path"):
        if st.button("Ghi đè file JSON hiện tại", use_container_width=True, icon=":material/save:"):
            try:
                save_annotation(document, Path(document["json_path"]))
            except Exception as error:  # pragma: no cover - UI feedback
                set_flash("warning", f"Không lưu được file JSON: {error}")
            else:
                mark_clean()
                set_flash("success", f"Đã lưu vào {document['json_path']}.")
            st.rerun()

    if st.button("Đóng file và giải phóng RAM", use_container_width=True, icon=":material/close:"):
        st.session_state["_pending_document_unload"] = True
        set_flash("success", "Đã đóng file hiện tại và dọn cache/render state khỏi RAM.")
        st.rerun()

    status_text = "Có thay đổi chưa lưu" if document.get("dirty") else "Đã đồng bộ"
    st.caption(f":material/task_alt: Trạng thái: **{status_text}**")
    st.caption(f":material/picture_as_pdf: PDF: `{document['pdf_name']}`")
    st.caption(f":material/data_object: JSON: `{document['json_name']}`")



def render_editor_toolbar() -> None:
    st.caption("Thao tác nhanh: undo/redo và zoom gần vùng chỉnh sửa để thao tác đỡ phải kéo chuột xa.")

    with st.container(horizontal=True, horizontal_alignment="left", vertical_alignment="center"):
        if st.button("Undo", key="toolbar-undo", icon=":material/undo:", disabled=not can_undo()):
            if undo_last_action():
                set_flash("success", "Đã hoàn tác thao tác gần nhất.")
            st.rerun()

        if st.button("Redo", key="toolbar-redo", icon=":material/redo:", disabled=not can_redo()):
            if redo_last_action():
                set_flash("success", "Đã khôi phục thao tác vừa hoàn tác.")
            st.rerun()

        st.markdown(f"**{int(get_viewer_zoom() * 100)}%**")

        if st.button("-", key="zoom-out", disabled=get_viewer_zoom() <= 1.0, help="Thu nhỏ viewer"):
            zoom_out_viewer()
            st.rerun()

        if st.button("+", key="zoom-in", disabled=get_viewer_zoom() >= 3.0, help="Phóng to viewer"):
            zoom_in_viewer()
            st.rerun()

        if st.button("Fit", key="zoom-reset", help="Đưa zoom về 100%"):
            reset_viewer_zoom()
            st.rerun()



def show_document_summary(pdf_page_count: int) -> None:
    document = get_document()
    annotation = get_annotation()
    if document is None or annotation is None:
        return

    total_elements = get_total_element_count()
    annotation_page_count = get_page_count()
    current_elements = len(get_page_elements(st.session_state.current_page))

    header_col, badge_col = st.columns([5, 2], vertical_alignment="center")
    with header_col:
        st.title("PDF label studio")
        st.caption(
            "Hiển thị trực tiếp trang PDF, zoom/pan mượt trong viewer, kéo để move/resize bbox và cập nhật JSON ngay trong app.",
        )
    with badge_col:
        mode_label = "Chỉnh label" if st.session_state.mode == "edit" else "Tạo label mới"
        dirty_label = "Chưa lưu" if document.get("dirty") else "Đã lưu"
        st.markdown(f":blue-badge[{mode_label}] :orange-badge[{dirty_label}]")

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    metric_col1.metric("Tổng số trang PDF", pdf_page_count)
    metric_col2.metric("Trang trong JSON", annotation_page_count)
    metric_col3.metric("BBox ở trang hiện tại", current_elements)
    metric_col4.metric("Tổng số bbox", total_elements)

    if annotation_page_count != pdf_page_count:
        st.warning(
            "Số trang trong JSON khác với PDF. App vẫn render theo PDF và giữ nguyên cấu trúc JSON khi lưu.",
            icon=":material/warning:",
        )



def render_edit_panel(page_width: float, page_height: float) -> None:
    st.subheader("Chỉnh bbox đang chọn")
    selected = get_selected_element()

    if selected is None:
        st.info("Bấm vào một bbox trên viewer để chỉnh label, text và toạ độ.")
        return

    selected_id, element, page_number, _ = selected
    bbox = [float(value) for value in element.get("bbox", [0, 0, 0, 0])]
    label_options = ", ".join(get_label_choices())
    element_text = str(element.get("text", ""))
    element_figure_path = str(element.get("figure_path", ""))
    text_preview = element_text.replace("\n", " ").strip()
    text_preview = text_preview[:140] + ("…" if len(text_preview) > 140 else "")
    form_suffix = make_widget_state_suffix(
        {
            "selected_id": selected_id,
            "label": str(element.get("label", "text")),
            "bbox": bbox,
            "text_hash": hashlib.sha1(element_text.encode("utf-8")).hexdigest()[:10],
            "reading_order": int(element.get("reading_order", 0)),
            "figure_path": element_figure_path,
        }
    )

    st.caption(f"Trang {page_number} · ID {selected_id}")
    st.caption(f"Label hiện có: {label_options}")
    st.caption(f"Reading order hiện tại: {int(element.get('reading_order', 0))}")
    if text_preview:
        st.caption(f"Preview text: {text_preview}")
    if element_figure_path:
        st.caption(f"Figure path: {element_figure_path}")

    show_extended_fields = st.toggle(
        "Hiện trường mở rộng (text + metadata)",
        value=False,
        key=f"edit-advanced-toggle-{selected_id}",
        help="Mặc định chỉ load các trường cần sửa nhanh để panel bên phải nhẹ và đỡ lag hơn.",
    )

    with st.form(f"edit-form-{selected_id}"):
        label = st.text_input(
            "Tên label",
            value=str(element.get("label", "text")),
            key=f"edit-label-{form_suffix}",
        )

        coord_col1, coord_col2 = st.columns(2)
        with coord_col1:
            x0 = st.number_input(
                "x0",
                min_value=0.0,
                max_value=float(page_width),
                value=bbox[0],
                step=1.0,
                key=f"edit-x0-{form_suffix}",
            )
            y0 = st.number_input(
                "y0",
                min_value=0.0,
                max_value=float(page_height),
                value=bbox[1],
                step=1.0,
                key=f"edit-y0-{form_suffix}",
            )
        with coord_col2:
            x1 = st.number_input(
                "x1",
                min_value=0.0,
                max_value=float(page_width),
                value=bbox[2],
                step=1.0,
                key=f"edit-x1-{form_suffix}",
            )
            y1 = st.number_input(
                "y1",
                min_value=0.0,
                max_value=float(page_height),
                value=bbox[3],
                step=1.0,
                key=f"edit-y1-{form_suffix}",
            )

        if show_extended_fields:
            text = st.text_area(
                "Text",
                value=element_text,
                height=180,
                key=f"edit-text-{form_suffix}",
            )
            reading_order = st.number_input(
                "Reading order",
                value=int(element.get("reading_order", 0)),
                step=1,
                key=f"edit-reading-order-{form_suffix}",
            )
            figure_path = st.text_input(
                "Figure path (optional)",
                value=element_figure_path,
                key=f"edit-figure-path-{form_suffix}",
            )
        else:
            text = element_text
            reading_order = int(element.get("reading_order", 0))
            figure_path = element_figure_path

        action_col1, action_col2 = st.columns(2)
        with action_col1:
            save_clicked = st.form_submit_button("Cập nhật bbox", type="primary", use_container_width=True)
        with action_col2:
            delete_clicked = st.form_submit_button("Xóa bbox", use_container_width=True)

    if save_clicked:
        update_selected_element(
            label=label,
            bbox=[x0, y0, x1, y1],
            text=text,
            reading_order=int(reading_order),
            figure_path=figure_path,
            page_width=page_width,
            page_height=page_height,
        )
        set_flash("success", f"Đã cập nhật bbox {selected_id}.")
        st.rerun()

    if delete_clicked:
        delete_selected_element()
        set_flash("success", f"Đã xóa bbox {selected_id}.")
        st.rerun()



def render_create_panel(page_width: float, page_height: float) -> None:
    st.subheader("Tạo label mới")
    draft_bbox = st.session_state.get("draft_bbox")
    label_options = ", ".join(get_label_choices())

    if not draft_bbox:
        st.info("Chuyển sang chế độ tạo mới rồi kéo chuột trên vùng PDF để tạo một bbox mới.")
        return

    st.caption(f"BBox nháp: {', '.join(f'{value:.1f}' for value in draft_bbox)}")
    st.caption(f"Label hiện có: {label_options}")

    with st.form(f"create-form-page-{st.session_state.current_page}"):
        label = st.text_input("Tên label", value="text")

        coord_col1, coord_col2 = st.columns(2)
        with coord_col1:
            x0 = st.number_input("x0", min_value=0.0, max_value=float(page_width), value=float(draft_bbox[0]), step=1.0)
            y0 = st.number_input("y0", min_value=0.0, max_value=float(page_height), value=float(draft_bbox[1]), step=1.0)
        with coord_col2:
            x1 = st.number_input("x1", min_value=0.0, max_value=float(page_width), value=float(draft_bbox[2]), step=1.0)
            y1 = st.number_input("y1", min_value=0.0, max_value=float(page_height), value=float(draft_bbox[3]), step=1.0)

        text = st.text_area("Text", value="", height=180)
        reading_order = st.number_input(
            "Reading order",
            value=next_reading_order(st.session_state.current_page),
            step=1,
        )
        figure_path = st.text_input("Figure path (optional)", value="")

        action_col1, action_col2 = st.columns(2)
        with action_col1:
            add_clicked = st.form_submit_button("Thêm bbox", type="primary", use_container_width=True)
        with action_col2:
            clear_clicked = st.form_submit_button("Bỏ bbox nháp", use_container_width=True)

    if add_clicked:
        new_element_id = add_element(
            page_number=st.session_state.current_page,
            label=label,
            bbox=[x0, y0, x1, y1],
            text=text,
            reading_order=int(reading_order),
            figure_path=figure_path,
            page_width=page_width,
            page_height=page_height,
        )
        clear_draft_bbox()
        select_element(new_element_id)
        set_mode("edit")
        set_flash("success", f"Đã thêm bbox mới ở trang {st.session_state.current_page}.")
        st.rerun()

    if clear_clicked:
        clear_draft_bbox()
        set_flash("info", "Đã bỏ bbox nháp.")
        st.rerun()


with st.sidebar:
    st.title("PDF label studio")
    st.caption("Load PDF + JSON, zoom/pan ngay trong viewer và chỉnh bbox theo page-space để sẵn sàng deploy Streamlit.")
    render_local_loader()
    st.space("small")
    render_upload_loader()

show_flash_message()

document = get_document()
if document is None:
    st.title("PDF label studio")
    st.info(
        "Hãy load một cặp file PDF + JSON ở sidebar. App sẽ hiện PDF ở giữa và form chỉnh sửa ở panel bên phải.",
        icon=":material/upload_file:",
    )
    st.stop()

try:
    pdf_page_count = get_pdf_page_count(document["pdf_bytes"])
    if st.session_state.current_page > pdf_page_count:
        st.session_state.current_page = max(pdf_page_count, 1)

    image_src, page_width, page_height = render_page_as_data_uri(
        document["pdf_bytes"],
        st.session_state.current_page,
        render_scale=3.0,
    )
except Exception as error:  # pragma: no cover - UI feedback
    st.error(f"Không render được PDF: {error}", icon=":material/error:")
    st.stop()

viewer_component_key = get_viewer_component_key(document)
apply_pending_viewer_events(viewer_component_key, page_width, page_height)

with st.sidebar:
    render_document_controls(pdf_page_count)

show_document_summary(pdf_page_count)

viewer_col, editor_col = st.columns([5, 2], vertical_alignment="top")

with viewer_col:
    with st.container(border=True):
        st.subheader(f"Trang {st.session_state.current_page}")
        st.caption(
            "Mẹo: dùng nút zoom ở panel phải. Khi zoom lớn, cuộn để pan hoặc giữ Space rồi kéo. Ở edit mode có thể kéo bbox để move và kéo chấm góc để resize.",
        )
        color_map = get_label_colors()
        bbox_viewer(
            image_src=image_src,
            page_width=page_width,
            page_height=page_height,
            boxes=get_viewer_elements(st.session_state.current_page),
            mode=st.session_state.mode,
            selected_id=st.session_state.selected_element_id,
            colors=color_map,
            pending_box=st.session_state.draft_bbox if st.session_state.mode == "create" else None,
            zoom=get_viewer_zoom(),
            key=viewer_component_key,
        )

with editor_col:
    with st.container(border=True):
        render_editor_toolbar()

    st.space("small")

    with st.container(border=True):
        if st.session_state.mode == "edit":
            render_edit_panel(page_width, page_height)
        else:
            render_create_panel(page_width, page_height)
