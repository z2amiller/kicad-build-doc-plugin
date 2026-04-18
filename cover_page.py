"""Cover page: project title, board image slot, and controls list."""
from __future__ import annotations

import datetime
from typing import Callable, List, Optional, Tuple

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
) -> Tuple[List, _BoardImageSlot]:
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
