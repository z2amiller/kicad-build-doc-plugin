"""Cover page: project title, board image, and controls list."""

import datetime
import os
import shutil
import subprocess
from typing import Callable, List, Optional

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
    config = load_panel_config(board.name, plugin_dir, _log)
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
    """Export Edge.Cuts + silkscreen layers as SVG via kicad-cli.

    Uses --page-size-mode 2 (board area only) so the output is already
    cropped to the board outline with no page border.
    """
    _log = log or (lambda msg: None)

    board_path = board.name
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

    out_svg = os.path.join(tmpdir, "board_front.svg")
    layers = "Edge.Cuts,F.Mask,F.Paste,F.SilkS"

    env = os.environ.copy()
    env["DYLD_FRAMEWORK_PATH"] = "/Applications/KiCad/KiCad.app/Contents/Frameworks"
    env["DYLD_LIBRARY_PATH"] = "/Applications/KiCad/KiCad.app/Contents/Frameworks"

    result = subprocess.run(
        [
            cli, "pcb", "export", "svg",
            "--layers", layers,
            "--page-size-mode", "2",
            "--exclude-drawing-sheet",
            "--mode-single",
            "--output", out_svg,
            board_path,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )

    if result.returncode != 0 or not os.path.exists(out_svg):
        raise RuntimeError(
            f"kicad-cli SVG export failed (exit {result.returncode}): "
            f"{result.stderr.strip()[:300]}"
        )

    _log(f"  Board SVG exported: {out_svg}")
    return out_svg
