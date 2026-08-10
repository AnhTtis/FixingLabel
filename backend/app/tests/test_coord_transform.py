from app.services.coord_transform import (
    PageGeometry,
    ViewportTransform,
    image_to_pdf_bbox,
    image_to_viewport_bbox,
    pdf_to_image_bbox,
    viewport_to_image_bbox,
)


def test_pdf_image_round_trip() -> None:
    geometry = PageGeometry(pdf_width=595.0, pdf_height=842.0, image_width=1190.0, image_height=1684.0)
    bbox = [72.0, 80.0, 420.0, 130.0]

    image_bbox = pdf_to_image_bbox(bbox, geometry)
    restored_bbox = image_to_pdf_bbox(image_bbox, geometry)

    assert restored_bbox == bbox


def test_image_viewport_round_trip() -> None:
    viewport = ViewportTransform(scale=1.5, offset_x=20.0, offset_y=40.0)
    image_bbox = [144.0, 160.0, 840.0, 260.0]

    viewport_bbox = image_to_viewport_bbox(image_bbox, viewport)
    restored_bbox = viewport_to_image_bbox(viewport_bbox, viewport)

    assert restored_bbox == image_bbox
