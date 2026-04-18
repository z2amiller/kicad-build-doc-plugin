"""Cover page: project title, board image, and controls list."""

import datetime
import io
import os
import shutil
import subprocess
from typing import Callable, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Flowable, Paragraph, Spacer

from footprint_utils import extract_controls, get_board_path
from panel_config import load_panel_config
from pdf_utils import COL_ACCENT, COL_HEADER_BG, MARGIN, PAGE_H, PAGE_W, hr


class _BoardImageSlot(Flowable):
    """Invisible placeholder that records its absolute page position for pypdf overlay."""

    def __init__(self, width: float, height: float) -> None:
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.page_x: Optional[float] = None
        self.page_y: Optional[float] = None

    def draw(self) -> None:
        self.page_x, self.page_y = self.canv.absolutePosition(0, 0)


def build_cover_story(
    board,
    project_name: str,
    author: str,
    revision: str,
    tmpdir: str,
    plugin_dir: str,
    log: Optional[Callable] = None,
):
    _log = log or (lambda msg: None)
    story: List = []
    inner_w = PAGE_W - 2 * MARGIN

    title_style = ParagraphStyle(
        "CoverTitle",
        fontSize=28,
        leading=34,
        alignment=1,
        textColor=COL_HEADER_BG,
        fontName="Helvetica-Bold",
        spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        "CoverSub",
        fontSize=11,
        alignment=1,
        textColor=COL_ACCENT,
        fontName="Helvetica",
        spaceAfter=2,
    )

    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph(project_name, title_style))
    if author:
        story.append(Paragraph(author, sub_style))
    story.append(
        Paragraph(
            f"Revision {revision}  \u00b7  {datetime.date.today().strftime('%B %d, %Y')}",
            sub_style,
        )
    )
    story.append(Spacer(1, 0.2 * inch))
    story.append(hr(inner_w))
    story.append(Spacer(1, 0.25 * inch))

    slot = _BoardImageSlot(inner_w, PAGE_H * 0.55)
    story.append(slot)
    story.append(Spacer(1, 0.25 * inch))

    _log("Extracting controls…")
    config = load_panel_config(get_board_path(board), plugin_dir, _log)
    controls = extract_controls(board, set(config["footprints"].keys()))
    external = controls["external"]
    internal = controls["internal"]
    _log(f"  Found {len(external)} external, {len(internal)} internal control(s).")

    if external or internal:
        story.append(hr(inner_w))
        story.append(Spacer(1, 0.15 * inch))
        hdr_style = ParagraphStyle(
            "SecHdr",
            fontSize=13,
            fontName="Helvetica-Bold",
            textColor=COL_HEADER_BG,
            spaceAfter=4,
        )
        sub_hdr_style = ParagraphStyle(
            "SubHdr",
            fontSize=9,
            fontName="Helvetica-Bold",
            textColor=COL_ACCENT,
            spaceAfter=2,
            spaceBefore=6,
        )
        ctrl_style = ParagraphStyle(
            "Ctrl",
            fontSize=10,
            fontName="Helvetica",
            leading=15,
            leftIndent=12,
        )
        story.append(Paragraph("Controls &amp; Features", hdr_style))
        for section_label, items in [
            ("External Controls", external),
            ("Internal Controls", internal),
        ]:
            if not items:
                continue
            story.append(Paragraph(section_label, sub_hdr_style))
            for ctrl in items:
                story.append(
                    Paragraph(
                        f"\u2022 {ctrl['label']}"
                        f" <font color='grey' size='9'>({ctrl['value']})</font>",
                        ctrl_style,
                    )
                )

    return story, slot


def export_board_pdf(board, tmpdir: str, log: Optional[Callable] = None) -> str:
    """Export Edge.Cuts + silkscreen layers as a single-page PDF via kicad-cli."""
    _log = log or (lambda msg: None)

    board_path = get_board_path(board)
    if not board_path or not os.path.exists(board_path):
        raise RuntimeError(f"Board file not found at '{board_path}' — save the board first.")

    cli = shutil.which("kicad-cli") or next(
        (
            c
            for c in [
                "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
                "/usr/local/bin/kicad-cli",
                "/usr/bin/kicad-cli",
            ]
            if os.path.exists(c)
        ),
        None,
    )
    if not cli:
        raise RuntimeError("kicad-cli not found — cannot export board image.")

    out_pdf = os.path.join(tmpdir, "board_front.pdf")
    layers = "Edge.Cuts,F.Mask,F.Paste,F.SilkS"

    env = os.environ.copy()
    env["DYLD_FRAMEWORK_PATH"] = "/Applications/KiCad/KiCad.app/Contents/Frameworks"
    env["DYLD_LIBRARY_PATH"] = "/Applications/KiCad/KiCad.app/Contents/Frameworks"

    result = subprocess.run(
        [
            cli, "pcb", "export", "pdf",
            "--layers", layers,
            "--scale", "0",
            "--black-and-white",
            "--mode-single",
            "--output", out_pdf,
            board_path,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )

    if result.returncode != 0 or not os.path.exists(out_pdf):
        raise RuntimeError(
            f"kicad-cli PDF export failed (exit {result.returncode}): "
            f"{result.stderr.strip()[:300]}"
        )

    _log(f"  Board PDF exported: {out_pdf}")
    return out_pdf


def _board_pdf_content_bounds(board_page):
    """Return (x0, y0, x1, y1) of actual drawn content on the board PDF page.

    Uses a pypdf visitor to collect all path coordinates in device space.
    Falls back to the full mediabox if no path data is found.
    """
    xs = []
    ys = []

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
    """Return a BytesIO PDF with dimension arrows drawn outside the board bounds."""
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(page_w, page_h))

    GAP = 6       # pts between board edge and dimension line
    TICK = 5      # half-length of end tick marks
    FONT_SIZE = 7

    c.setStrokeColorRGB(0.25, 0.25, 0.25)
    c.setFillColorRGB(0.25, 0.25, 0.25)
    c.setLineWidth(0.5)
    c.setFont("Helvetica", FONT_SIZE)

    # ── Width dimension (above board) ────────────────────────────────────────
    y_line = top + GAP
    c.line(left, y_line, right, y_line)
    c.line(left,  y_line - TICK, left,  y_line + TICK)
    c.line(right, y_line - TICK, right, y_line + TICK)
    label_w = f"{width_mm:.1f} mm"
    mid_x = (left + right) / 2
    label_w_pts = c.stringWidth(label_w, "Helvetica", FONT_SIZE)
    pad = 2
    c.setFillColorRGB(1, 1, 1)
    c.rect(mid_x - label_w_pts / 2 - pad, y_line - FONT_SIZE / 2,
           label_w_pts + 2 * pad, FONT_SIZE, stroke=0, fill=1)
    c.setFillColorRGB(0.25, 0.25, 0.25)
    c.drawCentredString(mid_x, y_line - FONT_SIZE / 2 + 1, label_w)

    # ── Height dimension (left of board) ─────────────────────────────────────
    x_line = left - GAP
    c.line(x_line, bottom, x_line, top)
    c.line(x_line - TICK, bottom, x_line + TICK, bottom)
    c.line(x_line - TICK, top,    x_line + TICK, top)
    label_h = f"{height_mm:.1f} mm"
    mid_y = (bottom + top) / 2
    label_h_pts = c.stringWidth(label_h, "Helvetica", FONT_SIZE)
    c.saveState()
    c.translate(x_line - FONT_SIZE / 2 - 2, mid_y)
    c.rotate(90)
    c.setFillColorRGB(1, 1, 1)
    c.rect(-label_h_pts / 2 - pad, -FONT_SIZE / 2,
           label_h_pts + 2 * pad, FONT_SIZE, stroke=0, fill=1)
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
    """Overlay the board PDF scaled into the slot area on cover page 1 using pypdf."""
    from pypdf import PdfReader, PdfWriter, Transformation

    _log = log or (lambda msg: None)

    if slot.page_x is None:
        _log("  Board slot position not recorded — cover image skipped.")
        import shutil as _shutil
        _shutil.copy(cover_pdf_path, out_path)
        return

    board_reader = PdfReader(board_pdf_path)
    board_page = board_reader.pages[0]
    pdf_w = float(board_page.mediabox.width)
    pdf_h = float(board_page.mediabox.height)

    bounds = _board_pdf_content_bounds(board_page)
    if bounds:
        x0, y0, x1, y1 = bounds
        content_w = x1 - x0
        content_h = y1 - y0
        content_cx = (x0 + x1) / 2
        content_cy = (y0 + y1) / 2
        _log(f"  Board content bounds: ({x0:.1f},{y0:.1f})–({x1:.1f},{y1:.1f}), "
             f"size {content_w:.1f}×{content_h:.1f} pts")
    else:
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

    transform = Transformation().scale(scale, scale).translate(tx, ty)

    cover_reader = PdfReader(cover_pdf_path)
    cover_page_w = float(cover_reader.pages[0].mediabox.width)
    cover_page_h = float(cover_reader.pages[0].mediabox.height)

    writer = PdfWriter()
    writer.append(cover_reader)
    writer.pages[0].merge_transformed_page(board_page, transform)

    if board_size_mm and bounds:
        bw_mm, bh_mm = board_size_mm
        # Board content edges in cover-page coordinate space
        left   = x0 * scale + tx
        right  = x1 * scale + tx
        bottom = y0 * scale + ty
        top    = y1 * scale + ty
        _log(f"  Drawing dimension annotations: {bw_mm:.1f} × {bh_mm:.1f} mm")
        dim_buf = _dimension_overlay(
            cover_page_w, cover_page_h,
            left, right, bottom, top,
            bw_mm, bh_mm,
        )
        dim_page = PdfReader(dim_buf).pages[0]
        writer.pages[0].merge_page(dim_page)

    with open(out_path, "wb") as f:
        writer.write(f)
    _log("  Board image embedded on cover page.")
