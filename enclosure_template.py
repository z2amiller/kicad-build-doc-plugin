"""1:1 scale enclosure drilling template PDF generation."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from kipy.board import BoardLayer
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as rl_canvas

from footprint_utils import get_field, get_fp_id, safe_get_footprints, safe_get_shapes
from panel_config import FootprintHoleConfig, PanelConfig
from pdf_utils import MARGIN

MM = 72.0 / 25.4  # PDF points per mm
TOP_ROW_MM = 38.0  # enclosure Y of the topmost control row
NM_PER_MM = 1_000_000  # kipy uses nanometres


@dataclass
class TaydaHole:
    """One drilled hole in Tayda's coordinate system (mm from face centre)."""
    side: str        # "A" = front face, "B" = top face
    diameter_mm: float
    x_mm: float
    y_mm: float
    label: str = ""


def _board_bbox(board):
    """Return merged bounding box of all Edge.Cuts shapes as a kipy Box2, or None."""
    edge_shapes = [s for s in safe_get_shapes(board) if s.layer == BoardLayer.BL_Edge_Cuts]
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


class _EnclosureRenderer:
    """Renders a 1:1 enclosure drilling template onto a ReportLab canvas."""

    def __init__(
        self,
        c,
        ox: float,
        oy: float,
        fl: float,
        fb: float,
        fw: float,
        fh: float,
        td: float,
        board_cx: float,
        top_pcb_y: float,
        scale_mm: float = MM,
    ) -> None:
        self.c = c
        self.ox = ox
        self.oy = oy
        self.fl = fl
        self.fb = fb
        self.fw = fw
        self.fh = fh
        self.td = td
        self.board_cx = board_cx
        self.top_pcb_y = top_pcb_y
        self.scale_mm = scale_mm
        self.holes: List[TaydaHole] = []

    # ── Coordinate helpers ────────────────────────────────────────────────────

    def to_pdf(self, ex: float, ey: float):
        """Enclosure mm → PDF points."""
        return self.ox + ex * self.scale_mm, self.oy + ey * self.scale_mm

    def fp_to_enc(
        self,
        pcb_x: float,
        pcb_y: float,
        off_x: float = 0.0,
        off_y: float = 0.0,
    ):
        """PCB absolute mm → enclosure mm.

        X is mirrored around the board bounding-box centre (panel viewed from
        outside = PCB front mirrored).  Y is anchored so the topmost external
        control hole lands at TOP_ROW_MM above the enclosure centre.
        """
        return (
            -(pcb_x - self.board_cx) + off_x,
            (TOP_ROW_MM + self.top_pcb_y - pcb_y) + off_y,
        )

    # ── Drawing primitives ────────────────────────────────────────────────────

    def draw_hole(self, ex: float, ey: float, dia: float, label: str) -> None:
        """Draw a circle + crosshairs + labels at enclosure position (ex, ey)."""
        self.holes.append(TaydaHole(side="A", diameter_mm=dia, x_mm=ex, y_mm=ey, label=label))
        c = self.c
        smm = self.scale_mm
        hx, hy = self.to_pdf(ex, ey)
        r = (dia / 2) * smm
        cross = min(r + 1.5 * smm, 3.5 * smm)
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(0.4)
        c.circle(hx, hy, r, stroke=1, fill=0)
        c.setLineWidth(0.25)
        c.line(hx - cross, hy, hx + cross, hy)
        c.line(hx, hy - cross, hx, hy + cross)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 5)
        c.drawCentredString(hx, hy + r + 1.5 * smm, label)
        c.setFont("Helvetica", 4)
        c.drawCentredString(hx, hy - r - 3.0 * smm, f"\u00f8{dia:.1f} mm")

    # ── Structural drawing ────────────────────────────────────────────────────

    def draw_outline(self) -> None:
        """Draw the rounded-rect cross: face + 4 tabs."""
        c = self.c
        R = 3.0 * self.scale_mm
        fl, fb, fw, fh, td = self.fl, self.fb, self.fw, self.fh, self.td
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(0.75)
        c.roundRect(fl, fb, fw, fh, R, stroke=1, fill=0)  # face
        c.setLineWidth(0.5)
        c.roundRect(fl, fb + fh, fw, td, R, stroke=1, fill=0)  # top tab
        c.roundRect(fl, fb - td, fw, td, R, stroke=1, fill=0)  # bottom tab
        c.roundRect(fl - td, fb, td, fh, R, stroke=1, fill=0)  # left tab
        c.roundRect(fl + fw, fb, td, fh, R, stroke=1, fill=0)  # right tab

    def draw_face_rect(self) -> None:
        """Draw just the face outline (no tabs) — used for face-only preview."""
        c = self.c
        R = 3.0 * self.scale_mm
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(0.75)
        c.roundRect(self.fl, self.fb, self.fw, self.fh, R, stroke=1, fill=0)

    def draw_fold_lines(self) -> None:
        """Draw dashed lines at face boundary."""
        c = self.c
        fl, fb, fw, fh = self.fl, self.fb, self.fw, self.fh
        c.saveState()
        c.setDash([3, 3])
        c.setStrokeColorRGB(0.45, 0.45, 0.45)
        c.setLineWidth(0.4)
        c.line(fl, fb + fh, fl + fw, fb + fh)
        c.line(fl, fb, fl + fw, fb)
        c.line(fl, fb, fl, fb + fh)
        c.line(fl + fw, fb, fl + fw, fb + fh)
        c.restoreState()

    def draw_centre_lines(self, face_only: bool = False) -> None:
        """Draw dashed centre cross extending through tabs (or just the face)."""
        c = self.c
        fl, fb, fw, fh, td = self.fl, self.fb, self.fw, self.fh, self.td
        ox, oy = self.ox, self.oy
        ext = 0 if face_only else 5 * self.scale_mm
        c.saveState()
        c.setDash([4, 3])
        c.setStrokeColorRGB(0.65, 0.65, 0.65)
        c.setLineWidth(0.3)
        c.line(fl - td - ext, oy, fl + fw + td + ext, oy)
        c.line(ox, fb - td - ext, ox, fb + fh + td + ext)
        c.restoreState()

    # ── Hole groups ───────────────────────────────────────────────────────────

    def draw_footprint_holes(self, board, fp_config: Dict, log) -> None:
        """Iterate fp_config footprints and draw their holes."""
        for fp in safe_get_footprints(board, log):
            fp_id = get_fp_id(fp)
            if fp_id not in fp_config:
                continue
            cfg = fp_config[fp_id]
            ref_x = fp.position.x / NM_PER_MM
            ref_y = fp.position.y / NM_PER_MM
            if cfg.use_pad_centroid:
                try:
                    dx, dy = _pad_centroid_offset_mm(fp)
                    ref_x += dx
                    ref_y += dy
                except Exception:
                    pass
            rx, ry = self.fp_to_enc(ref_x, ref_y)
            ex = rx + cfg.offset_x
            ey = ry + cfg.offset_y
            label = cfg.label or get_field(fp, "Control") or fp.reference_field.text.value
            self.draw_hole(ex, ey, cfg.hole_dia, label)
            log(
                f"    {label}: ref ({rx:.2f}, {ry:.2f})"
                f"  offset ({cfg.offset_x:+.1f}, {cfg.offset_y:+.1f})"
                f"  hole ({ex:.2f}, {ey:.2f}) mm"
                + (" [centroid]" if cfg.use_pad_centroid else "")
            )

    def draw_led_holes(self, board, fp_config: Dict, log) -> None:
        """Draw holes for back-side LEDs/diodes not already in fp_config."""
        led_re = re.compile(r"^(D|LED)\d", re.IGNORECASE)
        for fp in safe_get_footprints(board, log):
            ref = fp.reference_field.text.value
            if not led_re.match(ref):
                continue
            if fp.layer != BoardLayer.BL_B_Cu:  # not flipped to back side
                continue
            fp_id = get_fp_id(fp)
            if fp_id in fp_config:  # already drawn by draw_footprint_holes
                continue
            cfg = fp_config.get(
                fp_id,
                FootprintHoleConfig(hole_dia=3.2, offset_x=0.0, offset_y=0.0, label="LED"),
            )
            ex, ey = self.fp_to_enc(
                fp.position.x / NM_PER_MM,
                fp.position.y / NM_PER_MM,
                cfg.offset_x,
                cfg.offset_y,
            )
            label = cfg.label or "LED"
            self.draw_hole(ex, ey, cfg.hole_dia, label)
            log(
                f"    LED (back-side {ref}): enc ({ex:.1f}, {ey:.1f}) mm"
                f"  \u00f8{cfg.hole_dia} mm"
            )

    def draw_side_b_holes(self, side_b: List, log) -> None:
        """Draw Side B (top face) holes on the top tab and record them for Tayda.

        Side B coordinate system: X positive = right, Y positive = front face.
        In the unfolded cross, Y positive = toward the front face = downward in the tab.
        """
        if not side_b:
            return
        smm = self.scale_mm
        enc_h = self.fh / smm   # face height in mm
        enc_d = self.td / smm   # depth in mm
        c = self.c
        # Label the top tab
        tab_cx_pt = self.ox
        tab_cy_pt = self.oy + (self.fh / 2 + self.td / 2)
        c.saveState()
        c.setFont("Helvetica-Oblique", 5)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.drawCentredString(tab_cx_pt, tab_cy_pt + self.td / 2 - 3.5 * smm, "SIDE B — TOP FACE")
        c.restoreState()
        for hole in side_b:
            self.holes.append(TaydaHole(
                side="B",
                diameter_mm=hole.diameter_mm,
                x_mm=hole.x_mm,
                y_mm=hole.y_mm,
                label=hole.label,
            ))
            enc_x = hole.x_mm
            enc_y = enc_h / 2 + enc_d / 2 - hole.y_mm
            hx, hy = self.to_pdf(enc_x, enc_y)
            dia = hole.diameter_mm
            r = (dia / 2) * smm
            cross = min(r + 1.5 * smm, 3.5 * smm)
            c.setStrokeColorRGB(0, 0, 0.7)
            c.setLineWidth(0.4)
            c.circle(hx, hy, r, stroke=1, fill=0)
            c.setLineWidth(0.25)
            c.line(hx - cross, hy, hx + cross, hy)
            c.line(hx, hy - cross, hx, hy + cross)
            c.setFillColorRGB(0, 0, 0.7)
            c.setFont("Helvetica", 5)
            c.drawCentredString(hx, hy + r + 1.5 * smm, hole.label)
            c.setFont("Helvetica", 4)
            c.drawCentredString(hx, hy - r - 3.0 * smm, f"\u00f8{dia:.1f} mm")
            log(f"    {hole.label} (Side B): ({hole.x_mm:.1f}, {hole.y_mm:.1f}) mm  \u00f8{dia} mm")

    def draw_fixed_holes(self, fixed_holes: List, log) -> None:
        """Draw fixed hole list."""
        for hole in fixed_holes:
            self.draw_hole(hole.x, hole.y, hole.dia, hole.label)
            log(
                f"    {hole.label} (fixed): ({hole.x:.1f}, {hole.y:.1f}) mm"
                f"  \u00f8{hole.dia} mm"
            )

    # ── Annotation ────────────────────────────────────────────────────────────

    def draw_title_block(
        self, project_name: str, enc_w: float, enc_h: float, preset: Optional[str] = None
    ) -> None:
        """Draw title + scale notice + 'PRINT AT 100%'."""
        c = self.c
        ox = self.ox
        fb, fh, td = self.fb, self.fh, self.td

        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 11)
        title_y = fb + fh + td + 10 * MM
        c.drawCentredString(
            ox, title_y, f"{project_name} \u2014 Enclosure Drilling Template"
        )
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(0.35, 0.35, 0.35)
        size_label = f"{preset} ({enc_w:.0f}\u00d7{enc_h:.0f} mm)" if preset else f"{enc_w:.0f} \u00d7 {enc_h:.0f} mm"
        c.drawCentredString(
            ox, title_y - 5 * MM, f"{size_label} enclosure"
        )

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

    def draw_scale_bar(self) -> None:
        """Draw a 25 mm reference bar below the notice."""
        c = self.c
        ox = self.ox
        fb, td = self.fb, self.td

        notice_y = fb - td - 7 * MM
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

    def draw_footer(
        self,
        project_name: str,
        author: str,
        page_num: int,
        total_pages: int,
    ) -> None:
        """Draw footer line + text."""
        c = self.c
        pw, _ph = letter
        footer_left = project_name
        if author:
            footer_left += f"  \u00b7  {author}"
        page_str = (
            f"Page {page_num} of {total_pages}"
            if total_pages
            else f"Page {page_num}"
        )
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.setLineWidth(0.4)
        c.line(MARGIN, 0.55 * inch, pw - MARGIN, 0.55 * inch)
        c.setFont("Helvetica", 7.5)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.drawString(MARGIN, 0.45 * inch, footer_left)
        c.drawRightString(pw - MARGIN, 0.45 * inch, page_str)


def generate_enclosure_pdf(
    board,
    config: PanelConfig,
    project_name: str,
    author: str,
    total_pages: int,
    page_num: int,
    out_path: str,
    log: Optional[Callable] = None,
    face_only: bool = False,
) -> List[TaydaHole]:
    """Render a 1:1 drilling template on a letter-size page.

    Layout is a cross/plus shape — the enclosure face in the centre with
    fold-out tabs on all four sides.  Fold lines are dashed.  Hole positions
    are derived from footprint PCB coordinates relative to the board-outline
    bounding-box centre.
    """
    _log = log or (lambda msg: None)
    enc = config.enclosure
    enc_w: float = enc.width
    enc_h: float = enc.height
    enc_d: float = enc.depth
    fp_config: Dict = config.footprints
    fixed_holes: List = config.fixed_holes

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

    if face_only:
        # Scale the face to fill the page (no wings, no scale bar).
        margin = 0.5 * inch
        avail_w = pw - 2 * margin
        avail_h = ph - 2 * margin
        s = min(avail_w / (enc_w * MM), avail_h / (enc_h * MM))
        scale_mm = MM * s
        ox = pw / 2
        oy = ph / 2
        fw = enc_w * scale_mm
        fh = enc_h * scale_mm
        fl = ox - fw / 2
        fb = oy - fh / 2
        td = 0.0
    else:
        # 1:1 scale centred on page, shifted down for title.
        scale_mm = MM
        ox = pw / 2
        oy = ph / 2 - 8 * MM
        fl = ox - (enc_w / 2) * MM
        fb = oy - (enc_h / 2) * MM
        fw = enc_w * MM
        fh = enc_h * MM
        td = enc_d * MM

    c = rl_canvas.Canvas(out_path, pagesize=letter)

    renderer = _EnclosureRenderer(
        c=c,
        ox=ox,
        oy=oy,
        fl=fl,
        fb=fb,
        fw=fw,
        fh=fh,
        td=td,
        board_cx=board_cx,
        top_pcb_y=top_pcb_y,
        scale_mm=scale_mm,
    )

    if face_only:
        renderer.draw_face_rect()
        renderer.draw_centre_lines(face_only=True)
    else:
        renderer.draw_outline()
        renderer.draw_fold_lines()
        renderer.draw_centre_lines()
    renderer.draw_footprint_holes(board, fp_config, _log)
    renderer.draw_led_holes(board, fp_config, _log)
    renderer.draw_fixed_holes(fixed_holes, _log)
    if not face_only:
        renderer.draw_side_b_holes(config.side_b, _log)
    if not face_only:
        renderer.draw_title_block(project_name, enc_w, enc_h, enc.preset)
        renderer.draw_scale_bar()
        renderer.draw_footer(project_name, author, page_num, total_pages)

    c.save()
    _log("  Enclosure template written.")
    return renderer.holes


def get_computed_holes(
    board,
    config: PanelConfig,
    log: Optional[Callable] = None,
) -> List[tuple]:
    """Return [(label, dia_mm, enc_x, enc_y)] for all footprint-derived and back-LED holes.

    Used by the drill editor to show auto-detected holes alongside fixed holes.
    Returns an empty list if the board outline cannot be determined.
    """
    _log = log or (lambda msg: None)
    try:
        bbox = _board_bbox(board)
        if bbox is None:
            return []
        board_cx = bbox.center().x / NM_PER_MM
        fp_config = config.footprints
        top_pcb_y = _find_top_anchor(board, fp_config)
        if top_pcb_y is None:
            top_pcb_y = bbox.center().y / NM_PER_MM

        r = _EnclosureRenderer(None, 0, 0, 0, 0, 0, 0, 0, board_cx, top_pcb_y)
        results: List[tuple] = []

        for fp in safe_get_footprints(board, _log):
            fp_id = get_fp_id(fp)
            if fp_id not in fp_config:
                continue
            cfg = fp_config[fp_id]
            ref_x = fp.position.x / NM_PER_MM
            ref_y = fp.position.y / NM_PER_MM
            if cfg.use_pad_centroid:
                try:
                    dx, dy = _pad_centroid_offset_mm(fp)
                    ref_x += dx
                    ref_y += dy
                except Exception:
                    pass
            rx, ry = r.fp_to_enc(ref_x, ref_y)
            ex, ey = rx + cfg.offset_x, ry + cfg.offset_y
            label = cfg.label or get_field(fp, "Control") or fp.reference_field.text.value
            results.append((label, cfg.hole_dia, ex, ey))

        led_re = re.compile(r"^(D|LED)\d", re.IGNORECASE)
        for fp in safe_get_footprints(board, _log):
            ref = fp.reference_field.text.value
            if not led_re.match(ref):
                continue
            if fp.layer != BoardLayer.BL_B_Cu:
                continue
            fp_id = get_fp_id(fp)
            if fp_id in fp_config:  # already included in fp_config loop above
                continue
            cfg = fp_config.get(fp_id, FootprintHoleConfig(hole_dia=3.2, offset_x=0.0, offset_y=0.0, label="LED"))
            ex, ey = r.fp_to_enc(fp.position.x / NM_PER_MM, fp.position.y / NM_PER_MM, cfg.offset_x, cfg.offset_y)
            results.append((cfg.label or "LED", cfg.hole_dia, ex, ey))

        return results
    except Exception as exc:
        _log(f"  get_computed_holes failed: {exc}")
        return []


def _pad_centroid_offset_mm(fp) -> tuple:
    """Return pad centroid as (dx, dy) offset from fp.position, in mm (PCB frame).

    Pad positions in fp.definition.pads are in the footprint's local coordinate
    system (nanometres). We rotate by fp.orientation to get the PCB-frame offset.
    Falls back to (0, 0) on any error or if no pads are present.
    """
    try:
        pads = list(fp.definition.pads)
    except AttributeError:
        return (0.0, 0.0)
    if not pads:
        return (0.0, 0.0)
    # kipy reports pad positions in absolute board coordinates (nanometres).
    # Subtract fp.position to get the offset from the footprint origin.
    cx = sum(p.position.x for p in pads) / len(pads) - fp.position.x
    cy = sum(p.position.y for p in pads) / len(pads) - fp.position.y
    # B_Cu footprints are mirrored: local X is negated in PCB space
    try:
        if fp.layer == BoardLayer.BL_B_Cu:
            cx = -cx
    except Exception:
        pass
    # rotate local offset into PCB frame using fp.orientation
    try:
        a = fp.orientation.to_radians()
        cos_a, sin_a = math.cos(a), math.sin(a)
        dx = (cos_a * cx - sin_a * cy) / NM_PER_MM
        dy = (sin_a * cx + cos_a * cy) / NM_PER_MM
    except Exception:
        dx = cx / NM_PER_MM
        dy = cy / NM_PER_MM
    return (dx, dy)


def _find_top_anchor(board, fp_config: Dict) -> Optional[float]:
    """Find the minimum effective PCB Y among external-control footprints.

    'Effective Y' is the footprint origin Y minus the enclosure offset_y, so
    we anchor on the topmost *hole* rather than the topmost footprint *origin*.
    """
    top_pcb_y: Optional[float] = None
    for fp in safe_get_footprints(board):
        fp_id = get_fp_id(fp)
        if fp_id not in fp_config:
            continue
        cfg = fp_config[fp_id]
        effective_y = fp.position.y / NM_PER_MM - cfg.offset_y
        if top_pcb_y is None or effective_y < top_pcb_y:
            top_pcb_y = effective_y
    return top_pcb_y
