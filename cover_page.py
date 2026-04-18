"""Cover page: project title, board image, and controls list."""

import datetime
import os
import shutil
import subprocess
from typing import Callable, List, Optional

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
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

    slot = _BoardImageSlot(inner_w, PAGE_H * 0.45)
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
            "--bg-color", "white",
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


def apply_board_pdf_to_cover(
    cover_pdf_path: str,
    board_pdf_path: str,
    slot: _BoardImageSlot,
    out_path: str,
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
    board_w = float(board_page.mediabox.width)
    board_h = float(board_page.mediabox.height)

    scale = min(slot.width / board_w, slot.height / board_h)
    tx = slot.page_x + (slot.width - scale * board_w) / 2
    ty = slot.page_y + (slot.height - scale * board_h) / 2
    _log(f"  Overlaying board PDF: scale={scale:.3f}, pos=({tx:.1f}, {ty:.1f})")

    transform = Transformation().scale(scale, scale).translate(tx, ty)

    cover_reader = PdfReader(cover_pdf_path)
    writer = PdfWriter()
    writer.append(cover_reader)
    writer.pages[0].merge_transformed_page(board_page, transform)

    with open(out_path, "wb") as f:
        writer.write(f)
    _log("  Board image embedded on cover page.")
