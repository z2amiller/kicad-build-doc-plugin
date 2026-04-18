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
from typing import Callable, Optional

import pcbnew
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, SimpleDocTemplate

from bom_pages import build_bom_story
from cover_page import build_cover_story
from enclosure_template import generate_enclosure_pdf
from panel_config import load_panel_config
from pdf_utils import MARGIN, make_page_footer, merge_pdfs
from schematic_export import export_schematic_pdf, stamp_schematic_footer


class BuildDocGenerator:
    def __init__(
        self,
        board: pcbnew.BOARD,
        params: dict,
        log: Optional[Callable] = None,
    ):
        self.board = board
        self.params = params
        self.project_name = params["project_name"]
        self.author = params.get("author", "")
        self.revision = params.get("revision", "1.0")
        self.output_path = params["output_path"]
        self.tmpdir = tempfile.mkdtemp(prefix="builddoc_")
        self._log = log or (lambda msg: None)
        self.total_pages = 0
        self._plugin_dir = os.path.dirname(os.path.realpath(__file__))

    def generate(self) -> None:
        body_pdf = os.path.join(self.tmpdir, "body.pdf")
        enc_pdf = os.path.join(self.tmpdir, "enclosure.pdf")
        has_body = self.params.get("include_cover") or self.params.get("include_bom")
        has_enc = self.params.get("include_enclosure")
        has_sch = self.params.get("include_sch")

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

        # Page order: body → schematic → enclosure template
        self.total_pages = body_count + sch_count + enc_count

        # ── Pass 2: re-render body with correct total for footer ───────────────
        parts = []
        if has_body:
            self._log(f"Finalising cover / BOM pages (pass 2, total {self.total_pages})…")
            self._render_body(body_pdf)
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
            config = load_panel_config(self.board.GetFileName(), self._plugin_dir, self._log)
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

    def _render_body(self, out_path: str) -> None:
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

        if self.params.get("include_cover"):
            story += build_cover_story(
                board=self.board,
                project_name=self.project_name,
                author=self.author,
                revision=self.revision,
                tmpdir=self.tmpdir,
                plugin_dir=self._plugin_dir,
                log=self._log,
            )

        if self.params.get("include_bom"):
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
