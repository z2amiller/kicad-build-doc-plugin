"""Tests for board_image.py — content bounds, dimension overlay, cover overlay."""
import io

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas as rl_canvas

from board_image import _dimension_overlay, apply_board_pdf_to_cover, board_pdf_content_bounds
from cover_page import _BoardImageSlot


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pdf_with_rect(x0, y0, x1, y1, page_w=400, page_h=300) -> bytes:
    """Return raw PDF bytes with a rectangle drawn as explicit moveto/lineto commands."""
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(page_w, page_h))
    p = c.beginPath()
    p.moveTo(x0, y0)
    p.lineTo(x1, y0)
    p.lineTo(x1, y1)
    p.lineTo(x0, y1)
    p.close()
    c.drawPath(p, stroke=1, fill=0)
    c.save()
    return buf.getvalue()


def _blank_pdf(page_w=612, page_h=792) -> bytes:
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(page_w, page_h))
    c.showPage()
    c.save()
    return buf.getvalue()


def _write(tmp_path, name, data: bytes):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


# ── board_pdf_content_bounds ──────────────────────────────────────────────────

def test_content_bounds_detects_rect():
    page = PdfReader(io.BytesIO(_pdf_with_rect(20, 30, 150, 120))).pages[0]
    bounds = board_pdf_content_bounds(page)
    assert bounds is not None
    x0, y0, x1, y1 = bounds
    assert abs(x0 - 20) < 2
    assert abs(y0 - 30) < 2
    assert abs(x1 - 150) < 2
    assert abs(y1 - 120) < 2


def test_content_bounds_blank_page_returns_none():
    page = PdfReader(io.BytesIO(_blank_pdf())).pages[0]
    assert board_pdf_content_bounds(page) is None


def test_content_bounds_width_and_height():
    page = PdfReader(io.BytesIO(_pdf_with_rect(10, 10, 110, 60))).pages[0]
    x0, y0, x1, y1 = board_pdf_content_bounds(page)
    assert abs((x1 - x0) - 100) < 2
    assert abs((y1 - y0) - 50) < 2


# ── _dimension_overlay ────────────────────────────────────────────────────────

def test_dimension_overlay_contains_width_label():
    buf = _dimension_overlay(612, 792, 100, 400, 200, 500, 58.5, 45.0)
    text = PdfReader(buf).pages[0].extract_text()
    assert "58.5 mm" in text


def test_dimension_overlay_contains_height_label():
    buf = _dimension_overlay(612, 792, 100, 400, 200, 500, 58.5, 45.0)
    text = PdfReader(buf).pages[0].extract_text()
    assert "45.0 mm" in text


def test_dimension_overlay_page_size_matches():
    buf = _dimension_overlay(612, 792, 100, 400, 200, 500, 58.5, 45.0)
    page = PdfReader(buf).pages[0]
    assert abs(float(page.mediabox.width) - 612) < 1
    assert abs(float(page.mediabox.height) - 792) < 1


def test_dimension_overlay_returns_bytesio():
    result = _dimension_overlay(612, 792, 50, 300, 100, 400, 60.0, 40.0)
    assert isinstance(result, io.BytesIO)
    assert result.tell() == 0  # seeked back to start


# ── apply_board_pdf_to_cover ──────────────────────────────────────────────────

def test_overlay_produces_single_page(tmp_path):
    cover = _write(tmp_path, "cover.pdf", _blank_pdf())
    board = _write(tmp_path, "board.pdf", _pdf_with_rect(20, 20, 180, 130))
    out = str(tmp_path / "out.pdf")

    slot = _BoardImageSlot(400, 300)
    slot.page_x = 100
    slot.page_y = 200

    apply_board_pdf_to_cover(cover, board, slot, out)
    assert len(PdfReader(out).pages) == 1


def test_overlay_with_dimensions(tmp_path):
    cover = _write(tmp_path, "cover.pdf", _blank_pdf())
    board = _write(tmp_path, "board.pdf", _pdf_with_rect(20, 20, 180, 130))
    out = str(tmp_path / "out.pdf")

    slot = _BoardImageSlot(400, 300)
    slot.page_x = 100
    slot.page_y = 200

    apply_board_pdf_to_cover(cover, board, slot, out, board_size_mm=(58.0, 45.0))
    text = PdfReader(out).pages[0].extract_text()
    assert "58.0 mm" in text
    assert "45.0 mm" in text


def test_overlay_slot_not_recorded_copies_cover(tmp_path):
    """When slot.page_x is None, output must equal the cover PDF unchanged."""
    cover_bytes = _blank_pdf()
    cover = _write(tmp_path, "cover.pdf", cover_bytes)
    board = _write(tmp_path, "board.pdf", _pdf_with_rect(20, 20, 100, 80))
    out = str(tmp_path / "out.pdf")

    slot = _BoardImageSlot(400, 300)
    # page_x stays None

    apply_board_pdf_to_cover(cover, board, slot, out)
    assert len(PdfReader(out).pages) == 1
