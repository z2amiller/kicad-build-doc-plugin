"""Drill editor dialog — edit fixed enclosure holes and preview the drilling template."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from typing import Any, List, Optional

import wx
import wx.dataview as dv

from footprint_utils import get_board_path
from panel_config import EnclosureConfig, FixedHole, PanelConfig, load_panel_config

COL_LABEL = 0
COL_DIA   = 1
COL_X     = 2
COL_Y     = 3

_WEBVIEW_AVAILABLE: Optional[bool] = None


def _check_webview() -> bool:
    global _WEBVIEW_AVAILABLE
    if _WEBVIEW_AVAILABLE is None:
        try:
            import wx.html2  # noqa: F401
            _WEBVIEW_AVAILABLE = True
        except Exception:
            _WEBVIEW_AVAILABLE = False
    return _WEBVIEW_AVAILABLE


class DrillEditorDialog(wx.Dialog):
    def __init__(self, parent, board, plugin_dir: str) -> None:
        super().__init__(parent, title="Edit Enclosure Drills", size=(760, 580),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.board = board
        self.plugin_dir = plugin_dir
        self._board_path = get_board_path(board)
        self._project_dir = os.path.dirname(self._board_path) if self._board_path else ""
        self._project_json = os.path.join(self._project_dir, "panel_config.json") if self._project_dir else ""

        # Load merged config as starting point
        merged = load_panel_config(self._board_path or "", plugin_dir)
        self._enclosure = merged.enclosure
        self._rows: List[FixedHole] = list(merged.fixed_holes)
        self._selected: Optional[int] = None
        self._updating = False
        self._preview_path: Optional[str] = None
        self._use_webview = _check_webview()

        self._build_ui()
        self._refresh_list()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        root = wx.BoxSizer(wx.HORIZONTAL)

        # ── Left pane: list + edit controls ───────────────────────
        left = wx.BoxSizer(wx.VERTICAL)

        # Enclosure dimensions row
        enc_row = wx.BoxSizer(wx.HORIZONTAL)
        enc_row.Add(wx.StaticText(panel, label="Enclosure (mm):"), flag=wx.ALIGN_CENTER_VERTICAL)
        enc_row.AddSpacer(6)
        enc_row.Add(wx.StaticText(panel, label="W"), flag=wx.ALIGN_CENTER_VERTICAL)
        enc_row.AddSpacer(2)
        self._txt_enc_w = wx.TextCtrl(panel, value=f"{self._enclosure.width:.1f}", size=(52, -1))
        enc_row.Add(self._txt_enc_w, flag=wx.ALIGN_CENTER_VERTICAL)
        enc_row.AddSpacer(8)
        enc_row.Add(wx.StaticText(panel, label="H"), flag=wx.ALIGN_CENTER_VERTICAL)
        enc_row.AddSpacer(2)
        self._txt_enc_h = wx.TextCtrl(panel, value=f"{self._enclosure.height:.1f}", size=(52, -1))
        enc_row.Add(self._txt_enc_h, flag=wx.ALIGN_CENTER_VERTICAL)
        enc_row.AddSpacer(8)
        enc_row.Add(wx.StaticText(panel, label="D"), flag=wx.ALIGN_CENTER_VERTICAL)
        enc_row.AddSpacer(2)
        self._txt_enc_d = wx.TextCtrl(panel, value=f"{self._enclosure.depth:.1f}", size=(52, -1))
        enc_row.Add(self._txt_enc_d, flag=wx.ALIGN_CENTER_VERTICAL)
        left.Add(enc_row, flag=wx.ALL, border=8)

        # DataViewListCtrl
        self._dvc = dv.DataViewListCtrl(panel, style=dv.DV_SINGLE | dv.DV_ROW_LINES)
        self._dvc.AppendTextColumn("Label",   width=140, mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("Dia (mm)", width=70,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("X (mm)",  width=70,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("Y (mm)",  width=70,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.Bind(dv.EVT_DATAVIEW_SELECTION_CHANGED, self._on_selection)
        left.Add(self._dvc, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        # Add / Delete buttons
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        btn_add = wx.Button(panel, label="Add Hole")
        btn_del = wx.Button(panel, label="Delete")
        btn_add.Bind(wx.EVT_BUTTON, self._on_add)
        btn_del.Bind(wx.EVT_BUTTON, self._on_delete)
        btn_row.Add(btn_add, flag=wx.RIGHT, border=6)
        btn_row.Add(btn_del)
        left.Add(btn_row, flag=wx.ALL, border=8)

        # Edit panel
        edit_box = wx.StaticBox(panel, label="Edit selected hole")
        edit_sizer = wx.StaticBoxSizer(edit_box, wx.VERTICAL)
        grid = wx.FlexGridSizer(cols=4, vgap=6, hgap=8)
        grid.AddGrowableCol(1, 1)

        def _lbl(text):
            return wx.StaticText(panel, label=text)

        grid.Add(_lbl("Label:"),   flag=wx.ALIGN_CENTER_VERTICAL)
        self._txt_label = wx.TextCtrl(panel, size=(120, -1))
        grid.Add(self._txt_label, flag=wx.EXPAND)

        grid.Add(_lbl("Dia (mm):"), flag=wx.ALIGN_CENTER_VERTICAL)
        self._txt_dia = wx.TextCtrl(panel, size=(70, -1))
        grid.Add(self._txt_dia)

        grid.Add(_lbl("X (mm):"),  flag=wx.ALIGN_CENTER_VERTICAL)
        self._txt_x = wx.TextCtrl(panel, size=(70, -1))
        grid.Add(self._txt_x)

        grid.Add(_lbl("Y (mm):"),  flag=wx.ALIGN_CENTER_VERTICAL)
        self._txt_y = wx.TextCtrl(panel, size=(70, -1))
        grid.Add(self._txt_y)

        edit_sizer.Add(grid, flag=wx.EXPAND | wx.ALL, border=6)

        hint = wx.StaticText(panel, label="X/Y: mm from enclosure centre. +X = right, +Y = up.")
        hint.SetForegroundColour(wx.Colour(100, 100, 100))
        hint.SetFont(hint.GetFont().Scaled(0.85))
        edit_sizer.Add(hint, flag=wx.LEFT | wx.BOTTOM, border=6)

        left.Add(edit_sizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        for ctrl in (self._txt_label, self._txt_dia, self._txt_x, self._txt_y):
            ctrl.Bind(wx.EVT_TEXT, self._on_edit)
            ctrl.Enable(False)

        # Apply / Cancel / Preview buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._btn_preview = wx.Button(panel, label="Preview PDF")
        btn_apply  = wx.Button(panel, label="Apply")
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancel")
        btn_apply.SetDefault()
        self._btn_preview.Bind(wx.EVT_BUTTON, self._on_preview)
        btn_apply.Bind(wx.EVT_BUTTON, self._on_apply)
        btn_sizer.Add(self._btn_preview, flag=wx.RIGHT, border=6)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_apply, flag=wx.RIGHT, border=6)
        btn_sizer.Add(btn_cancel)
        left.Add(btn_sizer, flag=wx.EXPAND | wx.ALL, border=8)

        root.Add(left, proportion=1, flag=wx.EXPAND)

        # ── Right pane: WebView preview ────────────────────────────
        if self._use_webview:
            self._webview = wx.html2.WebView.New(panel, size=(340, -1))
            root.Add(self._webview, proportion=0, flag=wx.EXPAND | wx.RIGHT | wx.TOP | wx.BOTTOM, border=8)
            self._btn_preview.SetLabel("Refresh Preview")

        panel.SetSizer(root)
        self.Layout()

    # ── List management ───────────────────────────────────────────────────────

    def _refresh_list(self) -> None:
        self._dvc.DeleteAllItems()
        for h in self._rows:
            self._dvc.AppendItem([h.label, f"{h.dia:.2f}", f"{h.x:.2f}", f"{h.y:.2f}"])

    def _row_from_fields(self) -> Optional[FixedHole]:
        try:
            return FixedHole(
                label=self._txt_label.GetValue().strip(),
                dia=float(self._txt_dia.GetValue()),
                x=float(self._txt_x.GetValue()),
                y=float(self._txt_y.GetValue()),
            )
        except ValueError:
            return None

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_selection(self, event: Any) -> None:
        row = self._dvc.GetSelectedRow()
        if row < 0 or row >= len(self._rows):
            self._selected = None
            for ctrl in (self._txt_label, self._txt_dia, self._txt_x, self._txt_y):
                ctrl.Enable(False)
            return
        self._selected = row
        h = self._rows[row]
        self._updating = True
        self._txt_label.SetValue(h.label)
        self._txt_dia.SetValue(f"{h.dia:.2f}")
        self._txt_x.SetValue(f"{h.x:.2f}")
        self._txt_y.SetValue(f"{h.y:.2f}")
        self._updating = False
        for ctrl in (self._txt_label, self._txt_dia, self._txt_x, self._txt_y):
            ctrl.Enable(True)

    def _on_edit(self, event: Any) -> None:
        if self._updating or self._selected is None:
            return
        h = self._row_from_fields()
        if h is None:
            return
        self._rows[self._selected] = h
        row = self._selected
        self._dvc.SetTextValue(h.label,        row, COL_LABEL)
        self._dvc.SetTextValue(f"{h.dia:.2f}", row, COL_DIA)
        self._dvc.SetTextValue(f"{h.x:.2f}",  row, COL_X)
        self._dvc.SetTextValue(f"{h.y:.2f}",  row, COL_Y)

    def _on_add(self, event: Any) -> None:
        new_hole = FixedHole(label="New Hole", dia=8.0, x=0.0, y=0.0)
        self._rows.append(new_hole)
        self._dvc.AppendItem([new_hole.label, f"{new_hole.dia:.2f}",
                               f"{new_hole.x:.2f}", f"{new_hole.y:.2f}"])
        new_row = len(self._rows) - 1
        self._dvc.SelectRow(new_row)
        self._on_selection(None)
        self._txt_label.SetFocus()
        self._txt_label.SelectAll()

    def _on_delete(self, event: Any) -> None:
        if self._selected is None:
            return
        del self._rows[self._selected]
        self._selected = None
        self._refresh_list()
        for ctrl in (self._txt_label, self._txt_dia, self._txt_x, self._txt_y):
            ctrl.Enable(False)

    def _build_config(self) -> PanelConfig:
        """Build a PanelConfig from current dialog state (enclosure + fixed holes)."""
        try:
            enc = EnclosureConfig(
                width=float(self._txt_enc_w.GetValue()),
                height=float(self._txt_enc_h.GetValue()),
                depth=float(self._txt_enc_d.GetValue()),
            )
        except ValueError:
            enc = self._enclosure
        return PanelConfig(enclosure=enc, footprints={}, fixed_holes=list(self._rows))

    def _generate_preview_pdf(self) -> Optional[str]:
        """Generate enclosure PDF to a temp file and return its path, or None on error."""
        from enclosure_template import generate_enclosure_pdf
        config = self._build_config()
        # Merge footprints from the full merged config so PCB-derived holes appear too
        full = load_panel_config(self._board_path or "", self.plugin_dir)
        config = PanelConfig(enclosure=config.enclosure,
                             footprints=full.footprints,
                             fixed_holes=config.fixed_holes)
        try:
            tf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tf.close()
            generate_enclosure_pdf(
                board=self.board,
                config=config,
                project_name=os.path.basename(self._project_dir) if self._project_dir else "Preview",
                author="",
                total_pages=1,
                page_num=1,
                out_path=tf.name,
            )
            return tf.name
        except Exception as exc:
            wx.MessageBox(f"Preview failed:\n{exc}", "Preview Error", wx.OK | wx.ICON_WARNING)
            return None

    def _on_preview(self, event: Any) -> None:
        path = self._generate_preview_pdf()
        if not path:
            return
        if self._preview_path and self._preview_path != path:
            try:
                os.unlink(self._preview_path)
            except OSError:
                pass
        self._preview_path = path

        if self._use_webview:
            self._webview.LoadURL("file://" + path)
        else:
            # System viewer fallback
            if sys.platform == "darwin":
                subprocess.Popen(["open", path])
            elif sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", path])

    # ── Apply / save ──────────────────────────────────────────────────────────

    def _on_apply(self, event: Any) -> None:
        if not self._project_json:
            wx.MessageBox("Cannot determine project directory — board not saved.",
                          "Error", wx.OK | wx.ICON_ERROR)
            return

        try:
            enc_w = float(self._txt_enc_w.GetValue())
            enc_h = float(self._txt_enc_h.GetValue())
            enc_d = float(self._txt_enc_d.GetValue())
        except ValueError:
            wx.MessageBox("Enclosure dimensions must be numbers.", "Invalid Input",
                          wx.OK | wx.ICON_WARNING)
            return

        # Load existing project JSON (if any) to preserve other keys (e.g. footprints)
        existing: dict = {}
        if os.path.exists(self._project_json):
            try:
                with open(self._project_json) as fh:
                    existing = json.load(fh)
            except Exception:
                pass

        existing["enclosure"] = {"width": enc_w, "height": enc_h, "depth": enc_d}
        existing["fixed_holes"] = [
            {"label": h.label, "dia": h.dia, "x": h.x, "y": h.y}
            for h in self._rows
        ]

        with open(self._project_json, "w") as fh:
            json.dump(existing, fh, indent=2)

        self.EndModal(wx.ID_OK)

    def Destroy(self) -> bool:
        if self._preview_path:
            try:
                os.unlink(self._preview_path)
            except OSError:
                pass
        return super().Destroy()
