from __future__ import annotations

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
from labeling_app.pdf_render import get_pdf_page_count, render_page_as_data_uri
from labeling_app.state import (
    add_element,
    clear_draft_bbox,
    clear_selection,
    delete_selected_element,
    get_annotation,
    get_document,
    get_label_choices,
    get_label_colors,
    get_page_count,
    get_page_elements,
    get_selected_element,
    get_viewer_elements,
    init_app_state,
    load_document,
    make_element_id,
    mark_clean,
    next_reading_order,
    pop_flash,
    select_element,
    set_current_page,
    set_draft_bbox,
    set_flash,
    set_mode,
    update_element_bbox,
    update_selected_element,
)

st.set_page_config(
    page_title="PDF label studio",
    page_icon="🏷️",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_app_state()



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



def sync_visible_labels() -> list[str]:
    labels = get_label_choices()
    current = list(st.session_state.get("visible_labels", []))
    normalized = [label for label in current if label in labels]

    if not normalized and labels:
        normalized = labels.copy()

    new_labels = [label for label in labels if label not in normalized]
    merged = normalized + new_labels

    if merged != current:
        st.session_state.visible_labels = merged

    return labels



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

        load_document(document)
        set_flash("success", f"Đã load {uploaded_json.name} và {uploaded_pdf.name}.")
        st.rerun()



def render_document_controls(pdf_page_count: int) -> list[str]:
    document = get_document()
    annotation = get_annotation()
    if document is None or annotation is None:
        return []

    annotation["total_pages"] = max(int(annotation.get("total_pages") or 0), pdf_page_count)
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

    labels = sync_visible_labels()
    visible_labels = st.multiselect(
        "Label hiển thị",
        options=labels,
        key="visible_labels",
        help="Ẩn hoặc hiện bbox theo từng loại label.",
    )

    st.subheader("Lưu kết quả")
    export_bytes = export_annotation_bytes(annotation)
    suggested_name = document["json_name"].removesuffix(".json") + "_edited.json"
    st.download_button(
        "Tải JSON đã chỉnh",
        data=export_bytes,
        file_name=suggested_name,
        mime="application/json",
        use_container_width=True,
        icon=":material/download:",
    )

    if document.get("json_path"):
        if st.button("Ghi đè file JSON hiện tại", use_container_width=True, icon=":material/save:"):
            try:
                save_annotation(annotation, Path(document["json_path"]))
            except Exception as error:  # pragma: no cover - UI feedback
                set_flash("warning", f"Không lưu được file JSON: {error}")
            else:
                mark_clean()
                set_flash("success", f"Đã lưu vào {document['json_path']}.")
            st.rerun()

    status_text = "Có thay đổi chưa lưu" if document.get("dirty") else "Đã đồng bộ"
    st.caption(f":material/task_alt: Trạng thái: **{status_text}**")
    st.caption(f":material/picture_as_pdf: PDF: `{document['pdf_name']}`")
    st.caption(f":material/data_object: JSON: `{document['json_name']}`")

    return visible_labels



def show_document_summary(pdf_page_count: int) -> None:
    document = get_document()
    annotation = get_annotation()
    if document is None or annotation is None:
        return

    total_elements = sum(len(page.get("elements", [])) for page in annotation.get("pages", []))
    annotation_page_count = get_page_count()
    current_elements = len(get_page_elements(st.session_state.current_page))

    header_col, badge_col = st.columns([5, 2], vertical_alignment="center")
    with header_col:
        st.title("PDF label studio")
        st.caption(
            "Hiển thị trực tiếp trang PDF, click để chọn bbox, kéo thả để di chuyển/resize, và cập nhật JSON ngay trong app.",
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



def handle_viewer_events(viewer_result: dict[str, object], page_width: float, page_height: float) -> None:
    selected = viewer_result.get("selected")
    if isinstance(selected, str):
        if selected == "__clear__":
            clear_selection()
        else:
            select_element(selected)

    draft_payload = viewer_result.get("draft_bbox")
    if isinstance(draft_payload, dict):
        bbox = draft_payload.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            set_draft_bbox([float(value) for value in bbox])

    bbox_changed = viewer_result.get("bbox_changed")
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



def render_bbox_list_panel() -> None:
    st.subheader("Danh sách bbox trang hiện tại")
    elements = list(enumerate(get_page_elements(st.session_state.current_page)))

    if not elements:
        st.caption("Trang này chưa có bbox nào trong JSON.")
        return

    sorted_elements = sorted(
        elements,
        key=lambda item: (int(item[1].get("reading_order", item[0])), item[0]),
    )
    colors = get_label_colors()

    for element_index, element in sorted_elements:
        element_id = make_element_id(st.session_state.current_page, element_index)
        is_selected = element_id == st.session_state.selected_element_id
        label = str(element.get("label", "text"))
        reading_order = int(element.get("reading_order", element_index))
        preview = str(element.get("text", "")).replace("\n", " ").strip() or "(Không có text)"
        preview = preview[:110] + ("…" if len(preview) > 110 else "")
        color = colors.get(label, "#4159e3")
        button_label = f"{label} · RO {reading_order}"
        if is_selected:
            button_label = f"✓ {button_label}"

        cols = st.columns([1, 6], vertical_alignment="top")
        with cols[0]:
            st.markdown(
                f"<div style='width:14px;height:14px;margin-top:10px;border-radius:999px;background:{color};'></div>",
                unsafe_allow_html=True,
            )
        with cols[1]:
            if st.button(
                button_label,
                key=f"select-{element_id}",
                use_container_width=True,
                type="primary" if is_selected else "secondary",
            ):
                select_element(element_id)
                set_mode("edit")
                st.rerun()
            st.caption(preview)



def render_edit_panel(page_width: float, page_height: float) -> None:
    st.subheader("Chỉnh bbox đang chọn")
    selected = get_selected_element()

    if selected is None:
        st.info("Bấm vào một bbox ở giữa hoặc chọn từ danh sách bên phải để chỉnh label, text và toạ độ.")
        return

    selected_id, element, page_number, _ = selected
    bbox = [float(value) for value in element.get("bbox", [0, 0, 0, 0])]
    label_options = ", ".join(get_label_choices())

    st.caption(f"Trang {page_number} · ID {selected_id}")
    st.caption(f"Label hiện có: {label_options}")

    with st.form(f"edit-form-{selected_id}"):
        label = st.text_input("Tên label", value=str(element.get("label", "text")))

        coord_col1, coord_col2 = st.columns(2)
        with coord_col1:
            x0 = st.number_input("x0", min_value=0.0, max_value=float(page_width), value=bbox[0], step=1.0)
            y0 = st.number_input("y0", min_value=0.0, max_value=float(page_height), value=bbox[1], step=1.0)
        with coord_col2:
            x1 = st.number_input("x1", min_value=0.0, max_value=float(page_width), value=bbox[2], step=1.0)
            y1 = st.number_input("y1", min_value=0.0, max_value=float(page_height), value=bbox[3], step=1.0)

        text = st.text_area("Text", value=str(element.get("text", "")), height=180)
        reading_order = st.number_input(
            "Reading order",
            value=int(element.get("reading_order", 0)),
            step=1,
        )
        figure_path = st.text_input("Figure path (optional)", value=str(element.get("figure_path", "")))

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
    st.caption("Chuẩn bị sẵn cho việc deploy Streamlit: sample local, upload file, chỉnh trực tiếp và export JSON.")
    render_local_loader()
    st.space("small")
    render_upload_loader()

show_flash_message()

document = get_document()
if document is None:
    st.title("PDF label studio")
    st.info(
        "Hãy load một cặp file PDF + JSON ở sidebar. App sẽ hiện PDF ở giữa, danh sách bbox và form chỉnh sửa ở panel bên phải.",
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
        zoom=2.0,
    )
except Exception as error:  # pragma: no cover - UI feedback
    st.error(f"Không render được PDF: {error}", icon=":material/error:")
    st.stop()

with st.sidebar:
    visible_labels = render_document_controls(pdf_page_count)

show_document_summary(pdf_page_count)

viewer_col, editor_col = st.columns([5, 2], vertical_alignment="top")

with viewer_col:
    with st.container(border=True):
        st.subheader(f"Trang {st.session_state.current_page}")
        st.caption(
            "Mẹo: ở chế độ chỉnh sửa, kéo bbox để di chuyển và kéo chấm tròn ở góc để resize. Ở chế độ tạo mới, kéo chuột trên trang để tạo bbox.",
        )
        color_map = get_label_colors()
        viewer_result = bbox_viewer(
            image_src=image_src,
            page_width=page_width,
            page_height=page_height,
            boxes=get_viewer_elements(st.session_state.current_page, visible_labels),
            mode=st.session_state.mode,
            selected_id=st.session_state.selected_element_id,
            colors=color_map,
            pending_box=st.session_state.draft_bbox if st.session_state.mode == "create" else None,
            key=f"bbox-viewer-{document['doc_id']}-{st.session_state.current_page}",
        )
        handle_viewer_events(viewer_result, page_width, page_height)

        with st.expander("Màu label", expanded=False, icon=":material/palette:"):
            for label in get_label_choices():
                color = color_map[label]
                st.markdown(
                    f"<span style='display:inline-block;width:12px;height:12px;border-radius:999px;background:{color};margin-right:8px;'></span>{label}",
                    unsafe_allow_html=True,
                )

with editor_col:
    with st.container(border=True):
        render_bbox_list_panel()

    st.space("small")

    with st.container(border=True):
        if st.session_state.mode == "edit":
            render_edit_panel(page_width, page_height)
        else:
            render_create_panel(page_width, page_height)
