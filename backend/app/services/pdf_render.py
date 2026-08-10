from __future__ import annotations

from pathlib import Path

PdfSource = bytes | Path | str


def _fitz_module():
    try:
        import fitz  # type: ignore
    except ModuleNotFoundError as error:
        raise RuntimeError("PyMuPDF is required. Install the 'pymupdf' package to render PDF pages.") from error
    return fitz


def open_pdf(source: PdfSource):
    fitz = _fitz_module()
    if isinstance(source, bytes):
        return fitz.open(stream=source, filetype="pdf")
    return fitz.open(source)


def get_page_count(pdf_source: PdfSource) -> int:
    with open_pdf(pdf_source) as document:
        return len(document)


def get_page_size(pdf_source: PdfSource, page_number: int) -> tuple[float, float]:
    with open_pdf(pdf_source) as document:
        page = document[page_number - 1]
        return page.rect.width, page.rect.height


def render_page_png(pdf_source: PdfSource, page_number: int, scale: float = 1.5) -> bytes:
    fitz = _fitz_module()
    with open_pdf(pdf_source) as document:
        page = document[page_number - 1]
        matrix = fitz.Matrix(scale, scale)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        return pixmap.tobytes("png")


def render_thumbnail_png(pdf_source: PdfSource, page_number: int, scale: float = 0.3) -> bytes:
    return render_page_png(pdf_source, page_number, scale=scale)
