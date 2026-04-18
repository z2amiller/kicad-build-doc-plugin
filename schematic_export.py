"""Schematic PDF export and footer-stamping via kicad-cli."""
from __future__ import annotations

import io
import os
import subprocess
from typing import Callable, Optional

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas as rl_canvas

from cli_utils import find_kicad_cli, kicad_env
from footprint_utils import get_board_path


def export_schematic_pdf(
    board,
    params: dict,
    tmpdir: str,
    log: Optional[Callable] = None,
) -> Optional[str]:
    """Export the root schematic as a black-and-white PDF using kicad-cli.

    The root schematic is always derived from the board filename (same stem,
    .kicad_sch extension).  kicad-cli follows the hierarchy and includes all
    sub-sheets automatically.
    """
    _log = log or (lambda msg: None)
    board_path = get_board_path(board)
    canonical = os.path.splitext(board_path)[0] + ".kicad_sch"
    override = params.get("sch_path", "").strip()
    root_sch = canonical if os.path.exists(canonical) else (override or canonical)

    if not os.path.exists(root_sch):
        _log(f"  Root schematic not found at {root_sch} — skipped.")
        return None

    _log(f"  Root schematic: {os.path.basename(root_sch)}")

    cli = find_kicad_cli()
    if not cli:
        _log("  kicad-cli not found — schematic skipped.")
        return None

    out_pdf = os.path.join(tmpdir, "schematic.pdf")
    try:
        result = subprocess.run(
            [cli, "sch", "export", "pdf", "--black-and-white", "--output", out_pdf, root_sch],
            capture_output=True,
            text=True,
            timeout=120,
            env=kicad_env(),
        )
        if result.returncode == 0 and os.path.exists(out_pdf):
            _log("  Schematic exported OK.")
            return out_pdf
        _log(f"  kicad-cli failed (exit {result.returncode}): {result.stderr.strip()[:200]}")
    except Exception as e:
        _log(f"  kicad-cli error: {e}")

    return None


def stamp_schematic_footer(
    sch_pdf: str,
    start_page: int,
    total_pages: int,
    project_name: str,
    author: str,
    tmpdir: str,
    log: Optional[Callable] = None,
) -> str:
    """Overlay a project-name + global page-number footer on every schematic page."""
    _log = log or (lambda msg: None)

    reader = PdfReader(sch_pdf)
    writer = PdfWriter()
    stamped = os.path.join(tmpdir, "schematic_stamped.pdf")

    footer_left = project_name
    if author:
        footer_left += f"  \u00b7  {author}"

    # Shift footer lower than the body footer to clear the schematic frame
    y_line = (0.55 - 0.25) * 72
    y_text = (0.45 - 0.25) * 72
    margin = 0.65 * 72

    # Eagerly load all pages before modifying any — pypdf lazy-loading can
    # return stale references when iterating and mutating in a single pass.
    pages = [reader.pages[i] for i in range(len(reader.pages))]
    _log(f"  Stamping {len(pages)} schematic page(s)…")

    for i, page in enumerate(pages):
        pw = float(page.mediabox.width)
        ph = float(page.mediabox.height)
        _log(f"    Page {i + 1}: {pw:.0f} x {ph:.0f} pts")

        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=(pw, ph))
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.setLineWidth(0.4)
        c.line(margin, y_line, pw - margin, y_line)
        c.setFont("Helvetica", 7.5)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.drawString(margin, y_text, footer_left)
        c.drawRightString(pw - margin, y_text, f"Page {start_page + i} of {total_pages}")
        c.save()

        buf.seek(0)
        overlay_page = PdfReader(buf).pages[0]
        # Merge schematic page UNDER the overlay so the footer is always on top.
        overlay_page.merge_page(page)
        writer.add_page(overlay_page)

    with open(stamped, "wb") as fh:
        writer.write(fh)
    return stamped
