from __future__ import annotations

import base64

import fitz
import streamlit as st

from labeling_app.coordinates import get_page_scale_896, get_scaled_page_size


@st.cache_data(show_spinner=False)
def get_pdf_page_count(pdf_bytes: bytes) -> int:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        return document.page_count


@st.cache_data(show_spinner=False)
def get_pdf_page_metrics(pdf_bytes: bytes) -> list[dict[str, float | int]]:
    metrics: list[dict[str, float | int]] = []

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        for page_index, page in enumerate(document, start=1):
            page_width = float(page.rect.width)
            page_height = float(page.rect.height)
            scaled_width, scaled_height = get_scaled_page_size(page_width, page_height)
            metrics.append(
                {
                    "page_number": page_index,
                    "page_width": page_width,
                    "page_height": page_height,
                    "scale_896": get_page_scale_896(page_width, page_height),
                    "scaled_width": round(scaled_width, 2),
                    "scaled_height": round(scaled_height, 2),
                }
            )

    return metrics


@st.cache_data(show_spinner=False)
def render_page_as_data_uri(
    pdf_bytes: bytes,
    page_number: int,
    render_scale: float = 3.0,
) -> tuple[str, float, float]:
    page_index = max(page_number - 1, 0)

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        page = document.load_page(page_index)
        page_rect = page.rect
        pixmap = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale), alpha=False)
        png_bytes = pixmap.tobytes("png")

    data_uri = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
    return data_uri, float(page_rect.width), float(page_rect.height)



def clear_pdf_render_cache() -> None:
    get_pdf_page_count.clear()
    get_pdf_page_metrics.clear()
    render_page_as_data_uri.clear()
