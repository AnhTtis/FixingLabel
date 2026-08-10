from app.schemas.annotation import AnnotationElement, AnnotationPage
from app.services.coord_transform import PageGeometry
from app.services.editor_adapter import build_canvas_boxes, canvas_payload_to_patch_operations


def test_build_canvas_boxes_uses_label_metadata() -> None:
    page = AnnotationPage(
        page_number=1,
        width=200.0,
        height=100.0,
        elements=[
            AnnotationElement(id="e1", label="title", bbox=[20.0, 10.0, 100.0, 50.0]),
        ],
    )
    geometry = PageGeometry(pdf_width=200.0, pdf_height=100.0, image_width=400.0, image_height=200.0)

    boxes = build_canvas_boxes(
        page,
        geometry,
        {"labels": [{"id": "title", "name": "Title", "color": "#2563eb", "shortcut": "1"}]},
    )

    assert boxes[0]["id"] == "e1"
    assert boxes[0]["label_name"] == "Title"
    assert boxes[0]["left"] == 40.0
    assert boxes[0]["width"] == 160.0



def test_canvas_payload_to_patch_operations_updates_and_creates_boxes() -> None:
    page = AnnotationPage(
        page_number=1,
        width=200.0,
        height=100.0,
        elements=[
            AnnotationElement(id="e1", label="title", bbox=[20.0, 10.0, 100.0, 50.0]),
        ],
    )
    geometry = PageGeometry(pdf_width=200.0, pdf_height=100.0, image_width=400.0, image_height=200.0)

    payload = [
        {"id": "e1", "label": "title", "left": 60.0, "top": 20.0, "width": 160.0, "height": 80.0},
        {"label": "figure", "left": 200.0, "top": 40.0, "width": 80.0, "height": 60.0},
    ]

    operations, created_ids, missing_existing_ids = canvas_payload_to_patch_operations(
        page,
        geometry,
        payload,
        {"labels": [{"id": "title"}, {"id": "figure"}]},
    )

    assert len(operations) == 2
    assert operations[0].op == "update_bbox"
    assert operations[0].element_id == "e1"
    assert operations[0].bbox == [30.0, 10.0, 110.0, 50.0]
    assert operations[1].op == "create_element"
    assert operations[1].element.label == "figure"
    assert len(created_ids) == 1
    assert missing_existing_ids == []
