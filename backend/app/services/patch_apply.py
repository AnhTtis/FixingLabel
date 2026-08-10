from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.annotation import AnnotationDocument, AnnotationElement, PatchOperation


class PatchApplyError(ValueError):
    pass


MIN_BOX_SIZE = 1.0


def _get_page(document: AnnotationDocument, page_number: int):
    for page in document.pages:
        if page.page_number == page_number:
            return page
    raise PatchApplyError(f"Page {page_number} does not exist")


def _get_element(page, element_id: str) -> AnnotationElement:
    for element in page.elements:
        if element.id == element_id:
            return element
    raise PatchApplyError(f"Element '{element_id}' does not exist on page {page.page_number}")


def _validate_bounds(page, bbox: list[float]) -> None:
    x0, y0, x1, y1 = bbox
    if x0 < 0 or y0 < 0 or x1 > page.width or y1 > page.height:
        raise PatchApplyError("Bounding box is outside the page bounds")
    if (x1 - x0) < MIN_BOX_SIZE or (y1 - y0) < MIN_BOX_SIZE:
        raise PatchApplyError("Bounding box is too small")


def apply_patches(document: AnnotationDocument, operations: list[PatchOperation]) -> AnnotationDocument:
    for operation in operations:
        page = _get_page(document, operation.page)

        if operation.op == "update_bbox":
            _validate_bounds(page, operation.bbox)
            element = _get_element(page, operation.element_id)
            element.bbox = operation.bbox
        elif operation.op == "update_label":
            element = _get_element(page, operation.element_id)
            element.label = operation.label
        elif operation.op == "create_element":
            _validate_bounds(page, operation.element.bbox)
            if any(existing.id == operation.element.id for existing in page.elements):
                raise PatchApplyError(f"Element '{operation.element.id}' already exists")
            page.elements.append(operation.element)
        elif operation.op == "delete_element":
            element = _get_element(page, operation.element_id)
            page.elements = [existing for existing in page.elements if existing.id != element.id]
        else:
            raise PatchApplyError(f"Unsupported patch operation '{operation.op}'")

    document.meta.version += 1
    document.meta.updated_at = datetime.now(timezone.utc)
    return document

