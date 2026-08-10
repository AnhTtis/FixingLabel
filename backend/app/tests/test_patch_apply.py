from datetime import datetime, timezone

import pytest

from app.schemas.annotation import AnnotationDocument, AnnotationMeta, AnnotationPage, AnnotationElement, BBoxPatch, LabelPatch
from app.services.patch_apply import PatchApplyError, apply_patches


@pytest.fixture
def annotation_document() -> AnnotationDocument:
    return AnnotationDocument(
        document_id="doc-1",
        source_pdf="sample.pdf",
        meta=AnnotationMeta(coord_space="pdf", version=1, updated_at=datetime.now(timezone.utc)),
        pages=[
            AnnotationPage(
                page_number=1,
                width=595.0,
                height=842.0,
                elements=[
                    AnnotationElement(id="p1_e1", label="title", bbox=[72.0, 80.0, 420.0, 130.0]),
                ],
            )
        ],
    )


def test_apply_bbox_patch(annotation_document: AnnotationDocument) -> None:
    updated = apply_patches(
        annotation_document,
        [BBoxPatch(op="update_bbox", page=1, element_id="p1_e1", bbox=[80.0, 90.0, 430.0, 140.0])],
    )

    assert updated.pages[0].elements[0].bbox == [80.0, 90.0, 430.0, 140.0]
    assert updated.meta.version == 2


def test_apply_label_patch(annotation_document: AnnotationDocument) -> None:
    updated = apply_patches(
        annotation_document,
        [LabelPatch(op="update_label", page=1, element_id="p1_e1", label="abstract")],
    )

    assert updated.pages[0].elements[0].label == "abstract"


def test_reject_out_of_bounds_bbox(annotation_document: AnnotationDocument) -> None:
    with pytest.raises(PatchApplyError):
        apply_patches(
            annotation_document,
            [BBoxPatch(op="update_bbox", page=1, element_id="p1_e1", bbox=[-1.0, 10.0, 420.0, 130.0])],
        )
