from __future__ import annotations

import base64

import fitz
import streamlit as st


@st.cache_data(show_spinner=False)
def get_pdf_page_count(pdf_bytes: bytes) -> int:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        return document.page_count


@st.cache_data(show_spinner=False)
def render_page_as_data_uri(pdf_bytes: bytes, page_number: int, zoom: float = 2.0) -> tuple[str, float, float]:
    page_index = max(page_number - 1, 0)

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        page = document.load_page(page_index)
        page_rect = page.rect
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        png_bytes = pixmap.tobytes("png")

    data_uri = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
    return data_uri, float(page_rect.width), float(page_rect.height)
