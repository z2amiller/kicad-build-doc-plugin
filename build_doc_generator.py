"""
Build Document Generator - orchestrator.
Produces a PedalPCB-style build document with:
  - Cover page  (board outline SVG + project name + controls list)
  - Parts list  (BOM from footprint attributes)
  - Schematic   (exported via kicad-cli, embedded as PDF pages)
  - Enclosure template  (1:1 drilling guide)
"""

import os
import tempfile
from dataclasses import dataclass
from typing import Callable, Optional

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, SimpleDocTemplate

@dataclass
class GeneratorParams:
    project_name: str
    output_path: str
    author: str = ""
    revision: str = "1.0"
    include_cover: bool = False
    include_bom: bool = False
    include_enclosure: bool = False
    include_sch: bool = False
    sch_path: str = ""


from board_image import apply_board_pdf_to_cover, export_board_pdf
from bom_pages import build_bom_story
from cover_page import build_cover_story
from enclosure_template import board_size_mm, generate_enclosure_pdf
from footprint_utils import get_board_path
from panel_config import load_panel_config
from pdf_utils import MARGIN, make_page_footer, merge_pdfs
from schematic_export import export_schematic_pdf, stamp_schematic_footer


class BuildDocGenerator:
    def __init__(
        self,
        board,
        params: GeneratorParams,
        log: Optional[Callable] = None,
    ):
        self.board = board
        self.params = params
        self.project_name = params.project_name
        self.author = params.author
        self.revision = params.revision
        self.output_path = params.output_path
        self.tmpdir = tempfile.mkdtemp(prefix="builddoc_")
        self._log = log or (lambda msg: None)
        self.total_pages = 0
        self._plugin_dir = os.path.dirname(os.path.realpath(__file__))

    def generate(self) -> None:
        body_pdf = os.path.join(self.tmpdir, "body.pdf")
        enc_pdf = os.path.join(self.tmpdir, "enclosure.pdf")
        has_body = self.params.include_cover or self.params.include_bom
        has_enc = self.params.include_enclosure
        has_sch = self.params.include_sch

        # ── Export board image PDF (independent of page count) ────────────────
        board_pdf_path = None
        if self.params.include_cover:
            self._log("Exporting board image…")
            try:
                board_pdf_path = export_board_pdf(self.board, self.tmpdir, self._log)
            except Exception as e:
                self._log(f"  Board image failed: {e}")

        # ── Pass 1: render body (page count unknown) and export schematic ──────
        body_count = 0
        if has_body:
            self._log("Generating cover / BOM pages (pass 1)…")
            self._render_body(body_pdf)
            body_count = len(PdfReader(body_pdf).pages)

        enc_count = 1 if has_enc else 0

        raw_sch = None
        sch_count = 0
        if has_sch:
            self._log("Exporting schematic…")
            raw_sch = export_schematic_pdf(self.board, self.params, self.tmpdir, self._log)
            if raw_sch:
                sch_count = len(PdfReader(raw_sch).pages)
            else:
                self._log("  Schematic export skipped.")

        # Page order: body (cover + BOM) → schematic → enclosure template
        self.total_pages = body_count + sch_count + enc_count

        # ── Pass 2: re-render body with correct total for footer ───────────────
        parts = []
        if has_body:
            self._log(f"Finalising cover / BOM pages (pass 2, total {self.total_pages})…")
            board_slot = self._render_body(body_pdf)

            if board_pdf_path and board_slot is not None:
                overlaid = os.path.join(self.tmpdir, "body_with_board.pdf")
                apply_board_pdf_to_cover(
                    body_pdf, board_pdf_path, board_slot, overlaid,
                    board_size_mm=board_size_mm(self.board),
                    log=self._log,
                )
                parts.append(overlaid)
            else:
                parts.append(body_pdf)

        if raw_sch:
            self._log("Stamping schematic footer…")
            stamped = stamp_schematic_footer(
                raw_sch,
                start_page=body_count + 1,
                total_pages=self.total_pages,
                project_name=self.project_name,
                author=self.author,
                tmpdir=self.tmpdir,
                log=self._log,
            )
            parts.append(stamped)

        if has_enc:
            self._log("Generating enclosure drilling template…")
            config = load_panel_config(get_board_path(self.board), self._plugin_dir, self._log)
            generate_enclosure_pdf(
                board=self.board,
                config=config,
                project_name=self.project_name,
                author=self.author,
                total_pages=self.total_pages,
                page_num=body_count + sch_count + 1,
                out_path=enc_pdf,
                log=self._log,
            )
            parts.append(enc_pdf)

        if not parts:
            raise RuntimeError("No pages were generated – enable at least one section.")

        self._log("Merging PDF…")
        merge_pdfs(parts, self.output_path)

    def _render_body(self, out_path: str):
        doc = SimpleDocTemplate(
            out_path,
            pagesize=letter,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=MARGIN,
        )
        styles = getSampleStyleSheet()
        story = []
        board_slot = None

        if self.params.include_cover:
            cover_story, board_slot = build_cover_story(
                board=self.board,
                project_name=self.project_name,
                author=self.author,
                revision=self.revision,
                tmpdir=self.tmpdir,
                plugin_dir=self._plugin_dir,
                log=self._log,
            )
            story += cover_story

        if self.params.include_bom:
            if story:
                story.append(PageBreak())
            story += build_bom_story(
                board=self.board,
                project_name=self.project_name,
                styles=styles,
                log=self._log,
            )

        footer_fn = make_page_footer(self.project_name, self.author, self.total_pages)
        doc.build(story, onFirstPage=footer_fn, onLaterPages=footer_fn)
        return board_slot
