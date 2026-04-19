"""
Build Document Generator - Dialog UI
"""
import tempfile
import wx
import os
from typing import Optional

from footprint_utils import get_board_path
from panel_config import load_blurb

_WEBVIEW_AVAILABLE = None  # type: Optional[bool]


def _check_webview() -> bool:
    global _WEBVIEW_AVAILABLE
    if _WEBVIEW_AVAILABLE is None:
        try:
            import wx.html2  # noqa: F401
            _WEBVIEW_AVAILABLE = True
        except Exception:
            _WEBVIEW_AVAILABLE = False
    return _WEBVIEW_AVAILABLE


class BuildDocDialog(wx.Dialog):
    def __init__(self, parent, board):
        _ver_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
        _ver = open(_ver_file).read().strip() if os.path.exists(_ver_file) else "dev"
        self._use_webview = _check_webview()
        w = 820 if self._use_webview else 500
        super().__init__(parent, title=f"Build Document Generator v{_ver}", size=(w, 580))
        self.board = board
        self._preview_path: Optional[str] = None
        self._build_ui()

    def log(self, msg):
        self.txt_log.AppendText(msg + "\n")
        wx.SafeYield()

    def _build_ui(self):
        board = self.board
        board_path = get_board_path(board)
        board_name = os.path.splitext(os.path.basename(board_path))[0] if board_path else "Untitled"

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # ── Project info ─────────────────────────────────────────
        grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=10)
        grid.AddGrowableCol(1, 1)

        grid.Add(wx.StaticText(panel, label="Project Name:"), flag=wx.ALIGN_CENTER_VERTICAL)
        self.txt_name = wx.TextCtrl(panel, value=board_name)
        grid.Add(self.txt_name, flag=wx.EXPAND)

        grid.Add(wx.StaticText(panel, label="Author / Copyright:"), flag=wx.ALIGN_CENTER_VERTICAL)
        self.txt_author = wx.TextCtrl(panel, value="")
        grid.Add(self.txt_author, flag=wx.EXPAND)

        grid.Add(wx.StaticText(panel, label="Revision:"), flag=wx.ALIGN_CENTER_VERTICAL)
        self.txt_rev = wx.TextCtrl(panel, value="1.0")
        grid.Add(self.txt_rev, flag=wx.EXPAND)

        grid.Add(wx.StaticText(panel, label="Cover Blurb:"), flag=wx.ALIGN_TOP | wx.TOP, border=2)
        project_dir = os.path.dirname(board_path) if board_path else ""
        default_blurb = load_blurb(project_dir) or ""
        self.txt_blurb = wx.TextCtrl(
            panel,
            value=default_blurb,
            style=wx.TE_MULTILINE,
            size=(-1, 54),
        )
        grid.Add(self.txt_blurb, flag=wx.EXPAND)

        vbox.Add(grid, flag=wx.EXPAND | wx.ALL, border=12)

        # ── Pages to include ─────────────────────────────────────
        box = wx.StaticBox(panel, label="Pages to Include")
        bsizer = wx.StaticBoxSizer(box, wx.VERTICAL)

        self.chk_cover = wx.CheckBox(panel, label="Cover Page  (project name + board outline + controls)")
        self.chk_bom   = wx.CheckBox(panel, label="Parts List  (BOM from board footprints)")
        self.chk_enc   = wx.CheckBox(panel, label="Enclosure Template  (1:1 drilling guide)")
        self.chk_tayda = wx.CheckBox(panel, label="Tayda Drill Manifest  (hole table for custom drilling order)")
        self.chk_sch   = wx.CheckBox(panel, label="Schematic   (exported from KiCad)")
        self.chk_cover.SetValue(True)
        self.chk_bom.SetValue(True)
        self.chk_enc.SetValue(True)
        self.chk_tayda.SetValue(True)
        self.chk_sch.SetValue(True)
        bsizer.Add(self.chk_cover, flag=wx.ALL, border=4)
        bsizer.Add(self.chk_bom,   flag=wx.ALL, border=4)
        bsizer.Add(self.chk_enc,   flag=wx.ALL, border=4)
        bsizer.Add(self.chk_tayda, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=4)
        bsizer.Add(self.chk_sch,   flag=wx.ALL, border=4)
        self.chk_enc.Bind(wx.EVT_CHECKBOX, self._on_enc_toggle)
        vbox.Add(bsizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=12)

        # ── Editor shortcuts ──────────────────────────────────────
        editor_row = wx.BoxSizer(wx.HORIZONTAL)
        btn_edit = wx.Button(panel, label="Edit Component Descriptions…")
        btn_edit.Bind(wx.EVT_BUTTON, self.on_edit_descriptions)
        editor_row.Add(btn_edit, flag=wx.RIGHT, border=8)
        btn_drills = wx.Button(panel, label="Edit Enclosure Drills…")
        btn_drills.Bind(wx.EVT_BUTTON, self.on_edit_drills)
        editor_row.Add(btn_drills)
        vbox.Add(editor_row, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=12)

        # ── Schematic path (optional override) ───────────────────
        sch_row = wx.BoxSizer(wx.HORIZONTAL)
        sch_row.Add(wx.StaticText(panel, label="Schematic (.kicad_sch):"), flag=wx.ALIGN_CENTER_VERTICAL)
        board_file = get_board_path(board)
        board_dir  = os.path.dirname(board_file) if board_file else ""
        # Prefer the schematic whose basename matches the board (the project root)
        default_sch = os.path.splitext(board_file)[0] + ".kicad_sch" if board_file else ""
        if not os.path.exists(default_sch):
            default_sch = ""
            for f in sorted(os.listdir(board_dir)) if board_dir else []:
                if f.endswith(".kicad_sch"):
                    default_sch = os.path.join(board_dir, f)
                    break
        self.txt_sch = wx.TextCtrl(panel, value=default_sch)
        btn_sch = wx.Button(panel, label="…", size=(30, -1))
        btn_sch.Bind(wx.EVT_BUTTON, self.on_browse_sch)
        sch_row.Add(self.txt_sch, proportion=1, flag=wx.LEFT | wx.RIGHT, border=6)
        sch_row.Add(btn_sch)
        vbox.Add(sch_row, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=12)

        # ── Output path ──────────────────────────────────────────
        out_row = wx.BoxSizer(wx.HORIZONTAL)
        out_row.Add(wx.StaticText(panel, label="Output PDF:"), flag=wx.ALIGN_CENTER_VERTICAL)
        default_out = os.path.join(board_dir, board_name + "-BuildDoc.pdf") if board_dir else ""
        self.txt_out = wx.TextCtrl(panel, value=default_out)
        btn_out = wx.Button(panel, label="…", size=(30, -1))
        btn_out.Bind(wx.EVT_BUTTON, self.on_browse_out)
        out_row.Add(self.txt_out, proportion=1, flag=wx.LEFT | wx.RIGHT, border=6)
        out_row.Add(btn_out)
        vbox.Add(out_row, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=12)

        # ── Buttons ──────────────────────────────────────────────
        btn_sizer = wx.StdDialogButtonSizer()
        btn_gen = wx.Button(panel, label="Generate PDF")
        btn_gen.SetDefault()
        self.btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancel")
        btn_sizer.Add(btn_gen, flag=wx.RIGHT, border=8)
        btn_sizer.Add(self.btn_cancel)
        btn_gen.Bind(wx.EVT_BUTTON, self.on_generate)
        vbox.Add(btn_sizer, flag=wx.ALIGN_RIGHT | wx.ALL, border=12)

        # ── Log window ───────────────────────────────────────────
        vbox.Add(wx.StaticText(panel, label="Log:"), flag=wx.LEFT, border=12)
        self.txt_log = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.HSCROLL,
            size=(-1, 110),
        )
        self.txt_log.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        vbox.Add(self.txt_log, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=12)

        if self._use_webview:
            root = wx.BoxSizer(wx.HORIZONTAL)
            root.Add(vbox, proportion=0, flag=wx.EXPAND)
            self._webview = wx.html2.WebView.New(panel, size=(300, -1))
            root.Add(self._webview, proportion=0, flag=wx.EXPAND | wx.TOP | wx.RIGHT | wx.BOTTOM, border=8)
            panel.SetSizer(root)
            wx.CallAfter(self.refresh_preview)
        else:
            panel.SetSizer(vbox)
        self.Layout()

    def refresh_preview(self) -> None:
        if not self._use_webview:
            return
        try:
            from enclosure_template import generate_enclosure_pdf
            from panel_config import load_panel_config
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            board_path = get_board_path(self.board)
            config = load_panel_config(board_path or "", plugin_dir)
            tf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tf.close()
            generate_enclosure_pdf(
                board=self.board,
                config=config,
                project_name="Preview",
                author="",
                total_pages=1,
                page_num=1,
                out_path=tf.name,
                face_only=True,
            )
            if self._preview_path:
                try:
                    os.unlink(self._preview_path)
                except OSError:
                    pass
            self._preview_path = tf.name
            self._webview.LoadURL("file://" + tf.name)
        except Exception:
            pass  # preview is best-effort; don't interrupt the user

    def _on_enc_toggle(self, event):
        enabled = self.chk_enc.GetValue()
        self.chk_tayda.Enable(enabled)
        if not enabled:
            self.chk_tayda.SetValue(False)

    def on_edit_descriptions(self, event):
        from bulk_edit_dialog import BulkEditDialog
        dlg = BulkEditDialog(self, self.board)
        dlg.ShowModal()
        dlg.Destroy()

    def on_edit_drills(self, event):
        try:
            from drill_editor_dialog import DrillEditorDialog
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            dlg = DrillEditorDialog(self, self.board, plugin_dir)
            dlg.ShowModal()
            dlg.Destroy()
            self.refresh_preview()
        except Exception:
            import traceback
            wx.MessageBox(traceback.format_exc(), "Drill Editor Error", wx.OK | wx.ICON_ERROR)

    def on_browse_sch(self, event):
        dlg = wx.FileDialog(self, "Select Schematic", wildcard="KiCad Schematic (*.kicad_sch)|*.kicad_sch",
                            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self.txt_sch.SetValue(dlg.GetPath())
        dlg.Destroy()

    def on_browse_out(self, event):
        dlg = wx.FileDialog(self, "Save PDF As", wildcard="PDF files (*.pdf)|*.pdf",
                            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            self.txt_out.SetValue(dlg.GetPath())
        dlg.Destroy()

    def on_generate(self, event):
        from build_doc_generator import BuildDocGenerator, GeneratorParams

        params = GeneratorParams(
            project_name=self.txt_name.GetValue().strip() or "Untitled",
            author=self.txt_author.GetValue().strip(),
            revision=self.txt_rev.GetValue().strip(),
            blurb=self.txt_blurb.GetValue().strip(),
            include_cover=self.chk_cover.GetValue(),
            include_bom=self.chk_bom.GetValue(),
            include_enclosure=self.chk_enc.GetValue(),
            include_tayda=self.chk_tayda.GetValue(),
            include_sch=self.chk_sch.GetValue(),
            sch_path=self.txt_sch.GetValue().strip(),
            output_path=self.txt_out.GetValue().strip(),
        )

        if not params.output_path:
            wx.MessageBox("Please specify an output PDF path.", "Missing Output", wx.OK | wx.ICON_WARNING)
            return

        self.txt_log.Clear()
        try:
            gen = BuildDocGenerator(self.board, params, log=self.log)
            gen.generate()
            self.log(f"Done → {params.output_path}")
            self.btn_cancel.SetLabel("Close")
        except Exception:
            import traceback
            tb = traceback.format_exc()
            self.log("ERROR:\n" + tb)
