import fitz

from app.schemas.annotation import AnnotationDocument, AnnotationElement, AnnotationMeta, AnnotationPage
from app.services.annotation_io import (
    export_annotation_json,
    export_label_definitions_json,
    load_label_definitions,
    prepare_annotation,
    write_annotation_file,
    write_label_definitions_file,
)


def make_pdf_bytes() -> bytes:
    document = fitz.open()
    document.new_page(width=595.0, height=842.0)
    document.new_page(width=612.0, height=792.0)
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def test_prepare_annotation_syncs_page_sizes_and_missing_pages() -> None:
    annotation_text = """
    {
      "document_id": "sample-doc",
      "source_pdf": "old.pdf",
      "meta": {
        "coord_space": "pdf",
        "version": 1,
        "updated_at": "2026-07-28T00:00:00Z"
      },
      "pages": [
        {
          "page_number": 1,
          "width": 1,
          "height": 1,
          "elements": []
        }
      ]
    }
    """

    prepared = prepare_annotation("uploaded.pdf", make_pdf_bytes(), annotation_text)

    assert prepared.source_pdf == "uploaded.pdf"
    assert len(prepared.pages) == 2
    assert prepared.pages[0].width == 595.0
    assert prepared.pages[0].height == 842.0
    assert prepared.pages[1].width == 612.0
    assert prepared.pages[1].height == 792.0


def test_prepare_annotation_accepts_legacy_layout_json() -> None:
    annotation_text = """
    {
      "source_file": "/mnt/storage/lib_project/pdf_db/documents/HCMUS/2020/DangTruongSon/4.pdf",
      "total_pages": 2,
      "pages": [
        {
          "page_number": 1,
          "elements": [
            {
              "label": "section_header",
              "bbox": [204.0, 103.0, 450.0, 125.0],
              "text": "CHUONG 4",
              "reading_order": 0
            }
          ]
        },
        {
          "page_number": 2,
          "elements": [
            {
              "label": "text",
              "bbox": [102.0, 104.0, 577.0, 196.0],
              "text": "Legacy block",
              "reading_order": 0
            }
          ]
        }
      ]
    }
    """

    prepared = prepare_annotation("uploaded.pdf", make_pdf_bytes(), annotation_text)

    assert prepared.document_id.startswith("imported-")
    assert prepared.source_pdf == "uploaded.pdf"
    assert len(prepared.pages) == 2
    assert prepared.pages[0].elements[0].id == "p1_e1"
    assert prepared.pages[0].elements[0].text == "CHUONG 4"
    assert prepared.pages[0].elements[0].reading_order == 0
    assert prepared.pages[1].width == 612.0
    assert prepared.pages[1].height == 792.0


def test_prepare_annotation_normalizes_alternative_bbox_and_key_shapes() -> None:
    annotation_text = """
    {
      "doc_id": "legacy-doc",
      "pdf_path": "legacy.pdf",
      "document_pages": [
        {
          "index": 1,
          "blocks": [
            {
              "element_id": 99,
              "type": "text",
              "box": {"left": 10, "top": 20, "right": 110, "bottom": 220},
              "content": "Alternative keys",
              "order": 4
            },
            {
              "type": "list_item",
              "coordinates": {"x": 20, "y": 40, "width": 30, "height": 50}
            }
          ]
        }
      ]
    }
    """

    prepared = prepare_annotation("uploaded.pdf", make_pdf_bytes(), annotation_text)

    assert prepared.document_id == "legacy-doc"
    assert prepared.pages[0].elements[0].id == "99"
    assert prepared.pages[0].elements[0].bbox == [10.0, 20.0, 110.0, 220.0]
    assert prepared.pages[0].elements[0].text == "Alternative keys"
    assert prepared.pages[0].elements[0].reading_order == 4
    assert prepared.pages[0].elements[1].bbox == [20.0, 40.0, 50.0, 90.0]


def test_load_label_definitions_includes_unknown_annotation_labels() -> None:
    annotation = AnnotationDocument(
        document_id="doc-1",
        source_pdf="sample.pdf",
        meta=AnnotationMeta(),
        pages=[
            AnnotationPage(
                page_number=1,
                width=595.0,
                height=842.0,
                elements=[
                    AnnotationElement(id="e1", label="custom_label", bbox=[10.0, 20.0, 50.0, 60.0]),
                ],
            )
        ],
    )

    labels = load_label_definitions(annotation)
    custom_label = next(label for label in labels["labels"] if label["id"] == "custom_label")

    assert custom_label["name"] == "custom_label"
    assert custom_label["color"] == "#6b7280"



def test_load_label_definitions_uses_explicit_path(tmp_path) -> None:
    labels_path = tmp_path / "labels.json"
    labels_path.write_text(
        '{"labels": [{"id": "title", "name": "Paper Title", "color": "#2563eb", "shortcut": "1"}]}',
        encoding="utf-8",
    )

    labels = load_label_definitions(labels_path=labels_path)

    assert labels["labels"] == [
        {"id": "title", "name": "Paper Title", "color": "#2563eb", "shortcut": "1"},
    ]



def test_load_label_definitions_uses_payload_and_keeps_unknown_annotation_labels() -> None:
    annotation = AnnotationDocument(
        document_id="doc-1",
        source_pdf="sample.pdf",
        meta=AnnotationMeta(),
        pages=[
            AnnotationPage(
                page_number=1,
                width=595.0,
                height=842.0,
                elements=[
                    AnnotationElement(id="e1", label="custom_label", bbox=[10.0, 20.0, 50.0, 60.0]),
                ],
            )
        ],
    )

    labels = load_label_definitions(
        annotation,
        labels_payload={"labels": [{"id": "title", "name": "Paper Title", "color": "#2563eb", "shortcut": "1"}]},
    )

    assert labels["labels"][0] == {"id": "title", "name": "Paper Title", "color": "#2563eb", "shortcut": "1"}
    assert any(label["id"] == "custom_label" for label in labels["labels"])



def test_export_label_definitions_json_normalizes_display_names() -> None:
    exported = export_label_definitions_json(
        {
            "labels": [
                {"id": "title", "name": "Paper Title", "shortcut": "1", "color": "#2563eb"},
                {"id": "custom", "color": "#123456"},
            ]
        }
    )

    assert '"name": "Paper Title"' in exported
    assert '"id": "custom"' in exported
    assert '"name": "custom"' in exported



def test_export_annotation_json_contains_document_identity() -> None:
    annotation_text = """
    {
      "document_id": "sample-doc",
      "source_pdf": "paper.pdf",
      "meta": {
        "coord_space": "pdf",
        "version": 1,
        "updated_at": "2026-07-28T00:00:00Z"
      },
      "pages": [
        {
          "page_number": 1,
          "width": 595.0,
          "height": 842.0,
          "elements": []
        }
      ]
    }
    """

    prepared = prepare_annotation("paper.pdf", make_pdf_bytes(), annotation_text)
    exported = export_annotation_json(prepared)

    assert '"document_id": "sample-doc"' in exported
    assert '"source_pdf": "paper.pdf"' in exported



def test_write_annotation_file_persists_exported_json(tmp_path) -> None:
    annotation_text = """
    {
      "document_id": "sample-doc",
      "source_pdf": "paper.pdf",
      "meta": {
        "coord_space": "pdf",
        "version": 1,
        "updated_at": "2026-07-28T00:00:00Z"
      },
      "pages": [
        {
          "page_number": 1,
          "width": 595.0,
          "height": 842.0,
          "elements": []
        }
      ]
    }
    """
    prepared = prepare_annotation("paper.pdf", make_pdf_bytes(), annotation_text)

    output_path = tmp_path / "saved.annotations.json"
    written_path = write_annotation_file(prepared, output_path)

    assert written_path == output_path
    assert '"document_id": "sample-doc"' in output_path.read_text(encoding="utf-8")



def test_write_label_definitions_file_persists_normalized_labels(tmp_path) -> None:
    output_path = tmp_path / "labels.json"

    written_path = write_label_definitions_file(
        {"labels": [{"id": "title", "name": "Paper Title", "color": "#2563eb", "shortcut": "1"}]},
        output_path,
    )

    assert written_path == output_path
    assert '"name": "Paper Title"' in output_path.read_text(encoding="utf-8")
