"""1:1 scale enclosure drilling template PDF generation."""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as rl_canvas

from footprint_utils import get_field, get_fp_id
from pdf_utils import MARGIN

MM = 72.0 / 25.4  # PDF points per mm
TOP_ROW_MM = 38.0  # enclosure Y of the topmost control row
NM_PER_MM = 1_000_000  # kipy uses nanometres


def _board_bbox(board):
    """Return merged bounding box of all Edge.Cuts shapes as a kipy Box2, or None."""
    from kipy.board import BoardLayer
    edge_shapes = [s for s in board.get_shapes() if s.layer == BoardLayer.BL_Edge_Cuts]
    if not edge_shapes:
        return None
    bboxes = board.get_item_bounding_box(edge_shapes)
    if not bboxes:
        return None
    result = bboxes[0]
    for b in bboxes[1:]:
        result.merge(b)
    return result


def board_size_mm(board) -> Optional[tuple]:
    """Return (width_mm, height_mm) from the board's Edge.Cuts bounding box, or None."""
    try:
        bbox = _board_bbox(board)
        if bbox:
            return (bbox.size.x / NM_PER_MM, bbox.size.y / NM_PER_MM)
    except Exception:
        pass
    return None


def generate_enclosure_pdf(
    board,
    config: Dict,
    project_name: str,
    author: str,
    total_pages: int,
    page_num: int,
    out_path: str,
    log: Optional[Callable] = None,
) -> None:
    """Render a 1:1 drilling template on a letter-size page.

    Layout is a cross/plus shape — the enclosure face in the centre with
    fold-out tabs on all four sides.  Fold lines are dashed.  Hole positions
    are derived from footprint PCB coordinates relative to the board-outline
    bounding-box centre.
    """
    _log = log or (lambda msg: None)
    enc = config["enclosure"]
    enc_w: float = enc["width"]
    enc_h: float = enc["height"]
    enc_d: float = enc.get("depth", 35.0)
    fp_config: Dict = config["footprints"]
    fixed_holes: List = config["fixed_holes"]

    R = 3.0 * MM
    pw, ph = letter

    bbox = _board_bbox(board)
    if bbox is None:
        raise RuntimeError("No Edge.Cuts shapes found — cannot determine board outline.")
    board_cx = bbox.center().x / NM_PER_MM

    top_pcb_y = _find_top_anchor(board, fp_config)
    if top_pcb_y is None:
        top_pcb_y = bbox.center().y / NM_PER_MM
        _log("  No external controls found — falling back to board centre for Y.")
    else:
        _log(
            f"  Top control row anchor: effective pcb_y = {top_pcb_y:.2f} mm"
            f" → enc_y = {TOP_ROW_MM} mm"
        )

    # Enclosure origin in PDF coordinates — centred on the page, shifted 8 mm
    # down to leave room for the title above.
    ox = pw / 2
    oy = ph / 2 - 8 * MM

    def to_pdf(ex: float, ey: float):
        return ox + ex * MM, oy + ey * MM

    def fp_to_enc(pcb_x: float, pcb_y: float, off_x: float = 0.0, off_y: float = 0.0):
        """PCB absolute mm → enclosure mm.

        X is mirrored around the board bounding-box centre (panel viewed from
        outside = PCB front mirrored).  Y is anchored so the topmost external
        control hole lands at TOP_ROW_MM above the enclosure centre.
        """
        return (
            -(pcb_x - board_cx) + off_x,
            (TOP_ROW_MM + top_pcb_y - pcb_y) + off_y,
        )

    c = rl_canvas.Canvas(out_path, pagesize=letter)

    def draw_hole(ex: float, ey: float, dia: float, label: str) -> None:
        hx, hy = to_pdf(ex, ey)
        r = (dia / 2) * MM
        cross = min(r + 1.5 * MM, 3.5 * MM)
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(0.4)
        c.circle(hx, hy, r, stroke=1, fill=0)
        c.setLineWidth(0.25)
        c.line(hx - cross, hy, hx + cross, hy)
        c.line(hx, hy - cross, hx, hy + cross)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 5)
        c.drawCentredString(hx, hy + r + 1.5 * MM, label)
        c.setFont("Helvetica", 4)
        c.drawCentredString(hx, hy - r - 3.0 * MM, f"\u00f8{dia:.1f} mm")

    fl, fb = to_pdf(-enc_w / 2, -enc_h / 2)
    fw = enc_w * MM
    fh = enc_h * MM
    td = enc_d * MM

    # ── Cross of rounded rectangles ───────────────────────────────────────────
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(0.75)
    c.roundRect(fl, fb, fw, fh, R, stroke=1, fill=0)  # face

    c.setLineWidth(0.5)
    c.roundRect(fl, fb + fh, fw, td, R, stroke=1, fill=0)  # top tab
    c.roundRect(fl, fb - td, fw, td, R, stroke=1, fill=0)  # bottom tab
    c.roundRect(fl - td, fb, td, fh, R, stroke=1, fill=0)  # left tab
    c.roundRect(fl + fw, fb, td, fh, R, stroke=1, fill=0)  # right tab

    # ── Fold lines (dashed) at face boundary ──────────────────────────────────
    c.saveState()
    c.setDash([3, 3])
    c.setStrokeColorRGB(0.45, 0.45, 0.45)
    c.setLineWidth(0.4)
    c.line(fl, fb + fh, fl + fw, fb + fh)
    c.line(fl, fb, fl + fw, fb)
    c.line(fl, fb, fl, fb + fh)
    c.line(fl + fw, fb, fl + fw, fb + fh)
    c.restoreState()

    # ── Centre lines (extend through tabs) ────────────────────────────────────
    c.saveState()
    c.setDash([4, 3])
    c.setStrokeColorRGB(0.65, 0.65, 0.65)
    c.setLineWidth(0.3)
    ext = 5 * MM
    c.line(fl - td - ext, oy, fl + fw + td + ext, oy)
    c.line(ox, fb - td - ext, ox, fb + fh + td + ext)
    c.restoreState()

    # ── Footprint-driven holes ────────────────────────────────────────────────
    from kipy.board import BoardLayer

    for fp in board.get_footprints():
        fp_id = get_fp_id(fp)
        if fp_id not in fp_config:
            continue
        cfg = fp_config[fp_id]
        rx, ry = fp_to_enc(fp.position.x / NM_PER_MM, fp.position.y / NM_PER_MM)
        ex = rx + cfg["offset_x"]
        ey = ry + cfg["offset_y"]
        label = cfg["label"] or get_field(fp, "Control") or fp.reference_field.text.value
        draw_hole(ex, ey, cfg["hole_dia"], label)
        _log(
            f"    {label}: fp-origin ({rx:.2f}, {ry:.2f})"
            f"  offset ({cfg['offset_x']:+.1f}, {cfg['offset_y']:+.1f})"
            f"  hole ({ex:.2f}, {ey:.2f}) mm"
        )

    # ── Back-side LED/diode holes ─────────────────────────────────────────────
    led_re = re.compile(r"^(D|LED)\d", re.IGNORECASE)
    for fp in board.get_footprints():
        ref = fp.reference_field.text.value
        if not led_re.match(ref):
            continue
        if fp.layer != BoardLayer.BL_B_Cu:  # not flipped to back side
            continue
        fp_id = get_fp_id(fp)
        cfg = fp_config.get(
            fp_id, {"hole_dia": 3.2, "offset_x": 0.0, "offset_y": 0.0, "label": "LED"}
        )
        ex, ey = fp_to_enc(
            fp.position.x / NM_PER_MM,
            fp.position.y / NM_PER_MM,
            cfg["offset_x"],
            cfg["offset_y"],
        )
        label = cfg.get("label") or "LED"
        draw_hole(ex, ey, cfg["hole_dia"], label)
        _log(
            f"    LED (back-side {ref}): enc ({ex:.1f}, {ey:.1f}) mm"
            f"  \u00f8{cfg['hole_dia']} mm"
        )

    # ── Fixed holes ───────────────────────────────────────────────────────────
    for hole in fixed_holes:
        draw_hole(hole["x"], hole["y"], hole["dia"], hole["label"])
        _log(
            f"    {hole['label']} (fixed): ({hole['x']:.1f}, {hole['y']:.1f}) mm"
            f"  \u00f8{hole['dia']} mm"
        )

    # ── Title block ───────────────────────────────────────────────────────────
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 11)
    title_y = fb + fh + td + 10 * MM
    c.drawCentredString(ox, title_y, f"{project_name} \u2014 Enclosure Drilling Template")
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0.35, 0.35, 0.35)
    c.drawCentredString(ox, title_y - 5 * MM, f"{enc_w:.0f} \u00d7 {enc_h:.0f} mm enclosure")

    notice_y = fb - td - 7 * MM
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(0.78, 0, 0)
    c.drawCentredString(ox, notice_y, "PRINT AT 100% \u2014 DO NOT SCALE")
    c.setFont("Helvetica", 6.5)
    c.setFillColorRGB(0.45, 0.45, 0.45)
    c.drawCentredString(
        ox,
        notice_y - 4.5 * MM,
        "macOS: Print \u2192 Scale: 100%  \u2022  "
        "Verify scale bar below measures exactly 25 mm before drilling",
    )

    # ── Scale bar ─────────────────────────────────────────────────────────────
    bar_len = 25
    by0 = notice_y - 8 * MM
    bx0 = ox - bar_len / 2 * MM
    bx1 = bx0 + bar_len * MM
    tick = 1.5 * MM
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(0, 0, 0)
    c.setLineWidth(1.0)
    c.line(bx0, by0, bx1, by0)
    c.setLineWidth(0.5)
    c.line(bx0, by0 - tick, bx0, by0 + tick)
    c.line(bx1, by0 - tick, bx1, by0 + tick)
    c.setFont("Helvetica", 6)
    c.drawCentredString((bx0 + bx1) / 2, by0 - 4 * MM, f"{bar_len} mm")

    # ── Footer (matches body pages) ───────────────────────────────────────────
    footer_left = project_name
    if author:
        footer_left += f"  \u00b7  {author}"
    page_str = f"Page {page_num} of {total_pages}" if total_pages else f"Page {page_num}"
    c.setStrokeColorRGB(0.8, 0.8, 0.8)
    c.setLineWidth(0.4)
    c.line(MARGIN, 0.55 * inch, pw - MARGIN, 0.55 * inch)
    c.setFont("Helvetica", 7.5)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawString(MARGIN, 0.45 * inch, footer_left)
    c.drawRightString(pw - MARGIN, 0.45 * inch, page_str)

    c.save()
    _log("  Enclosure template written.")


def _find_top_anchor(board, fp_config: Dict) -> Optional[float]:
    """Find the minimum effective PCB Y among external-control footprints.

    'Effective Y' is the footprint origin Y minus the enclosure offset_y, so
    we anchor on the topmost *hole* rather than the topmost footprint *origin*.
    """
    top_pcb_y: Optional[float] = None
    for fp in board.get_footprints():
        fp_id = get_fp_id(fp)
        if fp_id not in fp_config:
            continue
        cfg = fp_config[fp_id]
        effective_y = fp.position.y / NM_PER_MM - cfg["offset_y"]
        if top_pcb_y is None or effective_y < top_pcb_y:
            top_pcb_y = effective_y
    return top_pcb_y
