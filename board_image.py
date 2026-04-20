"""Board PDF export, content-bounds detection, overlay, and dimension annotation."""

from __future__ import annotations

import io
import os
import subprocess
from typing import Callable, Optional, Tuple

from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.pdfgen import canvas as rl_canvas

from cli_utils import find_kicad_cli, kicad_env
from cover_page import _BoardImageSlot
from footprint_utils import get_board_path


def export_board_pdf(board, tmpdir: str, log: Optional[Callable] = None) -> str:
    """Export Edge.Cuts + silkscreen layers as a single-page PDF via kicad-cli."""
    _log = log or (lambda msg: None)

    board_path = get_board_path(board)
    if not board_path or not os.path.exists(board_path):
        raise RuntimeError(f"Board file not found at '{board_path}' — save the board first.")

    cli = find_kicad_cli()
    if not cli:
        raise RuntimeError("kicad-cli not found — cannot export board image.")

    out_pdf = os.path.join(tmpdir, "board_front.pdf")
    result = subprocess.run(
        [
            cli,
            "pcb",
            "export",
            "pdf",
            "--layers",
            "Edge.Cuts,F.Mask,F.Paste,F.SilkS",
            "--scale",
            "0",
            "--black-and-white",
            "--mode-single",
            "--output",
            out_pdf,
            board_path,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=kicad_env(),
    )

    if result.returncode != 0 or not os.path.exists(out_pdf):
        raise RuntimeError(
            f"kicad-cli PDF export failed (exit {result.returncode}): {result.stderr.strip()[:300]}"
        )

    _log(f"  Board PDF exported: {out_pdf}")
    return out_pdf


def board_pdf_content_bounds(
    board_page,
) -> Optional[Tuple[float, float, float, float]]:
    """Return (x0, y0, x1, y1) of actual drawn content in the board PDF page.

    Uses a pypdf visitor to collect path coordinates in device space.
    Returns None if no path data is found.
    """
    xs: list = []
    ys: list = []

    def _collect(op, args, cm, tm):
        if op in (b"m", b"l") and len(args) >= 2:
            a, b, c, d, e, f = cm
            x, y = float(args[-2]), float(args[-1])
            xs.append(a * x + c * y + e)
            ys.append(b * x + d * y + f)

    try:
        board_page.extract_text(visitor_operand_before=_collect)
    except Exception:
        pass

    if xs and ys:
        return min(xs), min(ys), max(xs), max(ys)
    return None


def _dimension_overlay(
    page_w: float,
    page_h: float,
    left: float,
    right: float,
    bottom: float,
    top: float,
    width_mm: float,
    height_mm: float,
) -> io.BytesIO:
    """Return a BytesIO PDF with dimension lines drawn outside the board bounds."""
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(page_w, page_h))

    GAP = 6
    TICK = 5
    FONT_SIZE = 7
    pad = 2

    c.setStrokeColorRGB(0.25, 0.25, 0.25)
    c.setFillColorRGB(0.25, 0.25, 0.25)
    c.setLineWidth(0.5)
    c.setFont("Helvetica", FONT_SIZE)

    # Width dimension (above board)
    y_line = top + GAP
    c.line(left, y_line, right, y_line)
    c.line(left, y_line - TICK, left, y_line + TICK)
    c.line(right, y_line - TICK, right, y_line + TICK)
    label_w = f"{width_mm:.1f} mm"
    mid_x = (left + right) / 2
    lw_pts = c.stringWidth(label_w, "Helvetica", FONT_SIZE)
    c.setFillColorRGB(1, 1, 1)
    c.rect(
        mid_x - lw_pts / 2 - pad,
        y_line - FONT_SIZE / 2,
        lw_pts + 2 * pad,
        FONT_SIZE,
        stroke=0,
        fill=1,
    )
    c.setFillColorRGB(0.25, 0.25, 0.25)
    c.drawCentredString(mid_x, y_line - FONT_SIZE / 2 + 1, label_w)

    # Height dimension (left of board)
    x_line = left - GAP
    c.line(x_line, bottom, x_line, top)
    c.line(x_line - TICK, bottom, x_line + TICK, bottom)
    c.line(x_line - TICK, top, x_line + TICK, top)
    label_h = f"{height_mm:.1f} mm"
    mid_y = (bottom + top) / 2
    lh_pts = c.stringWidth(label_h, "Helvetica", FONT_SIZE)
    c.saveState()
    c.translate(x_line - FONT_SIZE / 2 - 2, mid_y)
    c.rotate(90)
    c.setFillColorRGB(1, 1, 1)
    c.rect(-lh_pts / 2 - pad, -FONT_SIZE / 2, lh_pts + 2 * pad, FONT_SIZE, stroke=0, fill=1)
    c.setFillColorRGB(0.25, 0.25, 0.25)
    c.drawCentredString(0, -FONT_SIZE / 2 + 1, label_h)
    c.restoreState()

    c.save()
    buf.seek(0)
    return buf


def apply_board_pdf_to_cover(
    cover_pdf_path: str,
    board_pdf_path: str,
    slot: _BoardImageSlot,
    out_path: str,
    board_size_mm: Optional[Tuple[float, float]] = None,
    log: Optional[Callable] = None,
) -> None:
    """Overlay the board PDF scaled into the slot area on cover page 1."""
    _log = log or (lambda msg: None)

    if slot.page_x is None:
        _log("  Board slot position not recorded — cover image skipped.")
        import shutil

        shutil.copy(cover_pdf_path, out_path)
        return

    board_reader = PdfReader(board_pdf_path)
    board_page = board_reader.pages[0]
    pdf_w = float(board_page.mediabox.width)
    pdf_h = float(board_page.mediabox.height)

    bounds = board_pdf_content_bounds(board_page)
    if bounds:
        x0, y0, x1, y1 = bounds
        content_w = x1 - x0
        content_h = y1 - y0
        content_cx = (x0 + x1) / 2
        content_cy = (y0 + y1) / 2
        _log(
            f"  Board content bounds: ({x0:.1f},{y0:.1f})–({x1:.1f},{y1:.1f}), "
            f"size {content_w:.1f}×{content_h:.1f} pts"
        )
    else:
        x0 = y0 = x1 = y1 = None
        content_w = pdf_w
        content_h = pdf_h
        content_cx = pdf_w / 2
        content_cy = pdf_h / 2
        _log(f"  Board content: no path data, using full page {pdf_w:.1f}×{pdf_h:.1f}")

    scale = min(slot.width / content_w, slot.height / content_h)
    slot_cx = slot.page_x + slot.width / 2
    slot_cy = slot.page_y + slot.height / 2
    tx = slot_cx - scale * content_cx
    ty = slot_cy - scale * content_cy
    _log(f"  Overlaying board PDF: scale={scale:.3f}, pos=({tx:.1f}, {ty:.1f})")

    cover_reader = PdfReader(cover_pdf_path)
    cover_page_w = float(cover_reader.pages[0].mediabox.width)
    cover_page_h = float(cover_reader.pages[0].mediabox.height)

    writer = PdfWriter()
    writer.append(cover_reader)
    writer.pages[0].merge_transformed_page(
        board_page, Transformation().scale(scale, scale).translate(tx, ty)
    )

    if board_size_mm and bounds:
        bw_mm, bh_mm = board_size_mm
        left = x0 * scale + tx
        right = x1 * scale + tx
        bottom = y0 * scale + ty
        top = y1 * scale + ty
        _log(f"  Drawing dimension annotations: {bw_mm:.1f} × {bh_mm:.1f} mm")
        dim_page = PdfReader(
            _dimension_overlay(
                cover_page_w,
                cover_page_h,
                left,
                right,
                bottom,
                top,
                bw_mm,
                bh_mm,
            )
        ).pages[0]
        writer.pages[0].merge_page(dim_page)

    with open(out_path, "wb") as f:
        writer.write(f)
    _log("  Board image embedded on cover page.")
