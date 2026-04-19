"""Cover page: project title, board image slot, and controls list."""
from __future__ import annotations

import datetime
from typing import Callable, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Flowable, Paragraph, Spacer, Table, TableStyle

from footprint_utils import extract_controls, get_board_path
from panel_config import load_copyright, load_panel_config
from pdf_utils import COL_ACCENT, COL_HEADER_BG, MARGIN, PAGE_H, PAGE_W, hr

_CONTROLS_PER_COL = 4


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


def _controls_box(title: str, items: list, inner_w: float) -> Table:
    """Return a bordered multi-column Table for a controls section."""
    box_title_style = ParagraphStyle(
        "CtrlBoxTitle",
        fontSize=9,
        fontName="Helvetica-Bold",
        textColor=COL_HEADER_BG,
    )
    ctrl_style = ParagraphStyle(
        "CtrlItem",
        fontSize=9,
        fontName="Helvetica",
        leading=14,
    )

    # Split items into column chunks
    n = _CONTROLS_PER_COL
    chunks = [items[i:i + n] for i in range(0, len(items), n)]
    num_cols = len(chunks)
    max_rows = max(len(c) for c in chunks)
    col_w = inner_w / num_cols

    body_rows: List[list] = []
    for r in range(max_rows):
        row = []
        for chunk in chunks:
            if r < len(chunk):
                ctrl = chunk[r]
                cell = Paragraph(
                    f"\u2022 {ctrl.label}"
                    f" <font color='grey' size='8'>({ctrl.value})</font>",
                    ctrl_style,
                )
            else:
                cell = ""
            row.append(cell)
        body_rows.append(row)

    title_row = [Paragraph(title, box_title_style)] + [""] * (num_cols - 1)
    data = [title_row] + body_rows

    t = Table(data, colWidths=[col_w] * num_cols)
    t.setStyle(TableStyle([
        ("SPAN",         (0, 0), (-1, 0)),
        ("BOX",          (0, 0), (-1, -1), 0.5,  colors.HexColor("#cccccc")),
        ("LINEBELOW",    (0, 0), (-1, 0),  0.5,  colors.HexColor("#cccccc")),
        ("BACKGROUND",   (0, 0), (-1, 0),        colors.HexColor("#f5f5f5")),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def build_cover_story(
    board,
    project_name: str,
    author: str,
    revision: str,
    tmpdir: str,
    plugin_dir: str,
    blurb: str = "",
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
    copyright_text = load_copyright(plugin_dir)
    if copyright_text:
        copy_style = ParagraphStyle(
            "CoverCopyright",
            fontSize=8,
            alignment=1,
            textColor=COL_ACCENT,
            fontName="Helvetica",
            spaceAfter=4,
        )
        story.append(Paragraph(copyright_text.replace("\n", "<br/>"), copy_style))

    story.append(Spacer(1, 0.2 * inch))
    story.append(hr(inner_w))
    story.append(Spacer(1, 0.25 * inch))

    blurb_text = blurb.strip() or None
    board_slot_h = PAGE_H * (0.50 if blurb_text else 0.55)
    slot = _BoardImageSlot(inner_w, board_slot_h)
    story.append(slot)
    story.append(Spacer(1, 0.2 * inch))

    if blurb_text:
        blurb_style = ParagraphStyle(
            "CoverBlurb",
            fontSize=9,
            fontName="Helvetica",
            leading=14,
            spaceAfter=6,
        )
        story.append(Paragraph(blurb_text.replace("\n", "<br/>"), blurb_style))
        story.append(Spacer(1, 0.1 * inch))

    _log("Extracting controls…")
    config = load_panel_config(get_board_path(board), plugin_dir, _log)
    controls = extract_controls(board, set(config.footprints.keys()))
    external = controls.external
    internal = controls.internal
    _log(f"  Found {len(external)} external, {len(internal)} internal control(s).")

    if external or internal:
        story.append(hr(inner_w))
        story.append(Spacer(1, 0.15 * inch))
        if external and internal:
            # Side-by-side: col 0 gets box_w + gap colWidth with right-padding=gap
            # so both inner boxes receive exactly box_w usable space, total = inner_w.
            gap = 8
            box_w = (inner_w - gap) / 2
            side = Table(
                [[_controls_box("External Controls", external, box_w),
                  _controls_box("Internal Controls", internal, box_w)]],
                colWidths=[box_w + gap, box_w],
            )
            side.setStyle(TableStyle([
                ("VALIGN",        (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
                ("TOPPADDING",    (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING",  (0, 0), (0, -1),  gap),
            ]))
            story.append(side)
        elif external:
            story.append(_controls_box("External Controls", external, inner_w))
        else:
            story.append(_controls_box("Internal Controls", internal, inner_w))

    return story, slot
