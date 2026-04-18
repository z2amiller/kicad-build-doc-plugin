"""Cover page: project title, board image, and controls list."""

import datetime
import os
from typing import Callable, List, Optional

import pcbnew
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from footprint_utils import extract_controls
from panel_config import load_panel_config
from pdf_utils import COL_ACCENT, COL_HEADER_BG, MARGIN, PAGE_H, PAGE_W, hr


def build_cover_story(
    board,
    project_name: str,
    author: str,
    revision: str,
    tmpdir: str,
    plugin_dir: str,
    log: Optional[Callable] = None,
) -> List:
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

    note_style = ParagraphStyle(
        "Note",
        fontSize=9,
        alignment=1,
        textColor=colors.grey,
        fontName="Helvetica-Oblique",
    )
    _log("Exporting board image…")
    try:
        svg_path = export_board_image(board, tmpdir, _log)
        _log(f"  SVG written: {svg_path}")
        from svglib.svglib import svg2rlg

        drawing = svg2rlg(svg_path)
        if drawing is None:
            raise RuntimeError("svglib returned None for the SVG.")
        _log(f"  SVG dims from svglib: {drawing.width:.1f} x {drawing.height:.1f} pts")
        max_w = inner_w
        max_h = PAGE_H * 0.45
        scale = min(max_w / drawing.width, max_h / drawing.height)
        drawing.width *= scale
        drawing.height *= scale
        drawing.transform = (scale, 0, 0, scale, 0, 0)
        _log(f"  Rendered at {drawing.width:.1f} x {drawing.height:.1f} pts (scale {scale:.3f})")
        centered = Table([[drawing]], colWidths=[inner_w])
        centered.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        story.append(centered)
        story.append(Spacer(1, 0.25 * inch))
        _log("  Board image embedded OK.")
    except Exception as e:
        _log(f"  Board image failed: {e}")
        story.append(Paragraph(f"[Board image unavailable: {e}]", note_style))
        story.append(Spacer(1, 0.15 * inch))

    _log("Extracting controls…")
    config = load_panel_config(board.GetFileName(), plugin_dir, _log)
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

    return story


def export_board_image(board, tmpdir: str, log: Optional[Callable] = None) -> str:
    """Export Edge.Cuts + F.SilkS as SVG using pcbnew's in-process plot controller.

    Custom fields (LCSC numbers etc.) are temporarily hidden before plotting so
    they don't appear on the silkscreen layer.
    """
    _log = log or (lambda msg: None)
    hidden = []
    standard = {"Reference", "Value", "Footprint", "Datasheet"}
    for fp in board.GetFootprints():
        for field in fp.GetFields():
            try:
                if field.GetName() not in standard and field.IsVisible():
                    field.SetVisible(False)
                    hidden.append(field)
            except Exception:
                pass

    try:
        pctl = pcbnew.PLOT_CONTROLLER(board)
        popt = pctl.GetPlotOptions()
        popt.SetOutputDirectory(tmpdir)
        popt.SetPlotFrameRef(False)
        popt.SetAutoScale(False)
        popt.SetScale(1)
        popt.SetMirror(False)
        popt.SetUseAuxOrigin(False)
        popt.SetNegative(False)
        popt.SetPlotReference(True)
        popt.SetPlotValue(True)
        try:
            popt.SetDrillMarksType(pcbnew.DRILL_MARKS_FULL_DRILL_SHAPE)
        except Exception:
            pass
        pctl.SetColorMode(True)
        layers = [pcbnew.Edge_Cuts, pcbnew.F_Mask, pcbnew.F_Paste, pcbnew.F_SilkS]
        pctl.OpenPlotfile("board_front", pcbnew.PLOT_FORMAT_SVG, "Board Front")
        for layer in layers:
            pctl.SetLayer(layer)
            pctl.PlotLayer()
        pctl.ClosePlot()
    finally:
        for field in hidden:
            try:
                field.SetVisible(True)
            except Exception:
                pass

    svg_path = next(
        (os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.endswith(".svg")),
        None,
    )
    if not svg_path:
        raise RuntimeError("pcbnew plot controller ran but produced no SVG file.")

    try:
        import xml.etree.ElementTree as ET

        margin = 2.0
        bbox = board.GetBoardEdgesBoundingBox()
        vx = pcbnew.ToMM(bbox.GetX()) - margin
        vy = pcbnew.ToMM(bbox.GetY()) - margin
        vw = pcbnew.ToMM(bbox.GetWidth()) + 2 * margin
        vh = pcbnew.ToMM(bbox.GetHeight()) + 2 * margin
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        tree = ET.parse(svg_path)
        svg_el = tree.getroot()
        svg_el.set("viewBox", f"{vx:.3f} {vy:.3f} {vw:.3f} {vh:.3f}")
        svg_el.set("width", f"{vw:.3f}mm")
        svg_el.set("height", f"{vh:.3f}mm")
        tree.write(svg_path, xml_declaration=True, encoding="unicode")
        _log(f"  SVG cropped to board area: {vw:.1f} x {vh:.1f} mm")
    except Exception as e:
        _log(f"  SVG crop failed (using uncropped): {e}")

    return svg_path
