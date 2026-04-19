"""Drill editor dialog — edit fixed enclosure holes and preview the drilling template."""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

import wx
import wx.dataview as dv

from footprint_utils import get_board_path
from panel_config import (
    ENCLOSURE_PRESETS, EnclosureConfig, FixedHole, FootprintHoleConfig,
    PanelConfig, SideBHole, load_global_config, load_panel_config,
)


@dataclass
class _FpEntry:
    """One footprint-derived hole being displayed/edited in the drill editor."""
    fp_id: str
    reference: str        # e.g. "RV1" — unique instance identifier
    label: str
    hole_dia: float
    offset_x: float       # footprint-local offset (follows fp rotation)
    offset_y: float
    ref_enc_x: float      # enclosure coords of footprint origin, before offset (constant)
    ref_enc_y: float
    orientation_rad: float = 0.0   # fp board orientation, for offset rotation
    use_pad_centroid: bool = False
    excluded: bool = False         # True = write null override to project config

    @property
    def enc_x(self) -> float:
        cos_a = math.cos(self.orientation_rad)
        sin_a = math.sin(self.orientation_rad)
        return self.ref_enc_x + cos_a * self.offset_x - sin_a * self.offset_y

    @property
    def enc_y(self) -> float:
        cos_a = math.cos(self.orientation_rad)
        sin_a = math.sin(self.orientation_rad)
        return self.ref_enc_y + sin_a * self.offset_x + cos_a * self.offset_y

_PRESET_CHOICES = ["Custom"] + list(ENCLOSURE_PRESETS.keys())

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
        super().__init__(parent, title="Edit Enclosure Drills", size=(800, 820),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.board = board
        self.plugin_dir = plugin_dir
        self._board_path = get_board_path(board)
        self._project_dir = os.path.dirname(self._board_path) if self._board_path else ""
        self._project_json = os.path.join(self._project_dir, "panel_config.json") if self._project_dir else ""

        # Load from project file if it exists; otherwise seed from global template.
        self._global_config = load_global_config(plugin_dir)
        if self._project_json and os.path.exists(self._project_json):
            project = load_panel_config(self._board_path or "", plugin_dir)
            self._enclosure = project.enclosure
            self._rows: List[FixedHole] = list(project.fixed_holes)
            self._side_b: List[SideBHole] = list(project.side_b)
        else:
            self._enclosure = self._global_config.enclosure
            self._rows: List[FixedHole] = list(self._global_config.fixed_holes)
            self._side_b: List[SideBHole] = list(self._global_config.side_b)
        self._selected: Optional[int] = None
        self._fp_entries: List[_FpEntry] = []
        self._fp_selected: Optional[int] = None
        self._fp_originals: Dict[str, dict] = {}
        self._fp_preview_timer: Optional[wx.CallLater] = None
        self._updating = False
        self._preview_path: Optional[str] = None
        self._use_webview = _check_webview()

        self._build_ui()
        self._refresh_list()
        self._build_fp_entries()
        if self._use_webview:
            wx.CallAfter(self._on_preview, None)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        root = wx.BoxSizer(wx.HORIZONTAL)

        # ── Left pane: list + edit controls ───────────────────────
        left = wx.BoxSizer(wx.VERTICAL)

        # Enclosure size row
        enc_row = wx.BoxSizer(wx.HORIZONTAL)
        enc_row.Add(wx.StaticText(panel, label="Size:"), flag=wx.ALIGN_CENTER_VERTICAL)
        enc_row.AddSpacer(4)
        self._cho_preset = wx.Choice(panel, choices=_PRESET_CHOICES)
        preset_idx = (
            _PRESET_CHOICES.index(self._enclosure.preset)
            if self._enclosure.preset in _PRESET_CHOICES
            else 0
        )
        self._cho_preset.SetSelection(preset_idx)
        self._cho_preset.Bind(wx.EVT_CHOICE, self._on_preset_changed)
        enc_row.Add(self._cho_preset, flag=wx.ALIGN_CENTER_VERTICAL)
        enc_row.AddSpacer(12)
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

        # Top-face (Side B) layout picker
        layout_row = wx.BoxSizer(wx.HORIZONTAL)
        layout_row.Add(wx.StaticText(panel, label="Top face (Side B):"), flag=wx.ALIGN_CENTER_VERTICAL)
        layout_row.AddSpacer(6)
        self._cho_layout = wx.Choice(panel, choices=self._layout_names())
        self._cho_layout.SetSelection(0)
        layout_row.Add(self._cho_layout, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL)
        layout_row.AddSpacer(6)
        btn_apply_layout = wx.Button(panel, label="Apply Layout", size=(-1, -1))
        btn_apply_layout.Bind(wx.EVT_BUTTON, self._on_apply_layout)
        layout_row.Add(btn_apply_layout, flag=wx.ALIGN_CENTER_VERTICAL)
        left.Add(layout_row, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        # Auto-detected holes (selectable — select to edit its offset override)
        left.Add(wx.StaticText(panel, label="Auto-detected holes (from board footprints):"),
                 flag=wx.LEFT | wx.TOP, border=8)
        self._dvc_auto = dv.DataViewListCtrl(
            panel, style=dv.DV_SINGLE | dv.DV_ROW_LINES | dv.DV_NO_HEADER)
        self._dvc_auto.AppendTextColumn("Label",     width=120, mode=dv.DATAVIEW_CELL_INERT)
        self._dvc_auto.AppendTextColumn("Dia (mm)",  width=58,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc_auto.AppendTextColumn("X (mm)",    width=58,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc_auto.AppendTextColumn("Y (mm)",    width=58,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc_auto.AppendTextColumn("Off X",     width=50,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc_auto.AppendTextColumn("Off Y",     width=50,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc_auto.Bind(dv.EVT_DATAVIEW_SELECTION_CHANGED, self._on_fp_selection)
        left.Add(self._dvc_auto, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        auto_btn_row = wx.BoxSizer(wx.HORIZONTAL)
        btn_rules = wx.Button(panel, label="Manage Autodetect Rules…")
        btn_rules.Bind(wx.EVT_BUTTON, self._on_manage_rules)
        auto_btn_row.Add(btn_rules)
        left.Add(auto_btn_row, flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=8)

        # Edit footprint offset override (project-level)
        fp_box = wx.StaticBox(panel, label="Edit selected footprint override (project)")
        fp_sizer = wx.StaticBoxSizer(fp_box, wx.VERTICAL)
        fp_grid = wx.FlexGridSizer(cols=2, vgap=6, hgap=8)

        fp_grid.Add(wx.StaticText(panel, label="Hole Dia (mm):"), flag=wx.ALIGN_CENTER_VERTICAL)
        self._txt_fp_dia = wx.TextCtrl(panel, size=(70, -1))
        fp_grid.Add(self._txt_fp_dia)

        fp_grid.Add(wx.StaticText(panel, label="Offset X (mm):"), flag=wx.ALIGN_CENTER_VERTICAL)
        self._txt_fp_ox = wx.TextCtrl(panel, size=(70, -1))
        fp_grid.Add(self._txt_fp_ox)

        fp_grid.Add(wx.StaticText(panel, label="Offset Y (mm):"), flag=wx.ALIGN_CENTER_VERTICAL)
        self._txt_fp_oy = wx.TextCtrl(panel, size=(70, -1))
        fp_grid.Add(self._txt_fp_oy)

        fp_sizer.Add(fp_grid, flag=wx.ALL, border=6)
        fp_hint = wx.StaticText(
            panel,
            label="Offsets are in enclosure space (+X = right on panel, +Y = up) and rotate\n"
                  "with the footprint's board orientation. Apply saves to project.",
        )
        fp_hint.SetForegroundColour(wx.Colour(100, 100, 100))
        fp_hint.SetFont(fp_hint.GetFont().Scaled(0.85))
        fp_sizer.Add(fp_hint, flag=wx.LEFT | wx.BOTTOM, border=6)

        self._btn_fp_exclude = wx.Button(panel, label="Exclude from Holes")
        self._btn_fp_exclude.Bind(wx.EVT_BUTTON, self._on_fp_exclude)
        self._btn_fp_exclude.Enable(False)
        fp_sizer.Add(self._btn_fp_exclude, flag=wx.LEFT | wx.BOTTOM, border=6)

        left.Add(fp_sizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        for ctrl in (self._txt_fp_dia, self._txt_fp_ox, self._txt_fp_oy):
            ctrl.Bind(wx.EVT_TEXT, self._on_fp_edit)
            ctrl.Enable(False)

        # Fixed holes (editable)
        left.Add(wx.StaticText(panel, label="Fixed holes (manually specified):"),
                 flag=wx.LEFT | wx.TOP, border=8)
        self._dvc = dv.DataViewListCtrl(panel, style=dv.DV_SINGLE | dv.DV_ROW_LINES | dv.DV_NO_HEADER)
        self._dvc.AppendTextColumn("Label",    width=140, mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("Dia (mm)", width=70,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("X (mm)",   width=70,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("Y (mm)",   width=70,  mode=dv.DATAVIEW_CELL_INERT)
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

        # Top face (Side B) holes — read-only display
        left.Add(wx.StaticText(panel, label="Top face holes (Side B — use layout picker above to change):"),
                 flag=wx.LEFT, border=8)
        self._dvc_side_b = dv.DataViewListCtrl(
            panel, style=dv.DV_SINGLE | dv.DV_ROW_LINES | dv.DV_NO_HEADER)
        self._dvc_side_b.AppendTextColumn("Label",    width=140, mode=dv.DATAVIEW_CELL_INERT)
        self._dvc_side_b.AppendTextColumn("Dia (mm)", width=70,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc_side_b.AppendTextColumn("X (mm)",   width=70,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc_side_b.AppendTextColumn("Y (mm)",   width=70,  mode=dv.DATAVIEW_CELL_INERT)
        left.Add(self._dvc_side_b, proportion=0, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)
        self._refresh_side_b_list()

        # Apply / Cancel / Preview buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._btn_preview = wx.Button(panel, label="Preview PDF")
        btn_reset  = wx.Button(panel, label="Reset to Template")
        btn_apply  = wx.Button(panel, label="Apply")
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancel")
        btn_apply.SetDefault()
        self._btn_preview.Bind(wx.EVT_BUTTON, self._on_preview)
        btn_reset.Bind(wx.EVT_BUTTON, self._on_reset_template)
        btn_apply.Bind(wx.EVT_BUTTON, self._on_apply)
        btn_sizer.Add(self._btn_preview, flag=wx.RIGHT, border=6)
        btn_sizer.Add(btn_reset, flag=wx.RIGHT, border=6)
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

    def _layout_names(self) -> List[str]:
        """Return layout names for the current preset, or a placeholder if none."""
        preset = self._enclosure.preset
        if preset and preset in ENCLOSURE_PRESETS:
            layouts = ENCLOSURE_PRESETS[preset].get("side_b_layouts", [])
            if layouts:
                return [lay["name"] for lay in layouts]
        return ["(no layouts for this enclosure)"]

    def _refresh_layout_choices(self) -> None:
        self._cho_layout.Clear()
        for name in self._layout_names():
            self._cho_layout.Append(name)
        self._cho_layout.SetSelection(0)

    def _refresh_side_b_list(self) -> None:
        self._dvc_side_b.DeleteAllItems()
        for h in self._side_b:
            self._dvc_side_b.AppendItem([h.label, f"{h.diameter_mm:.2f}", f"{h.x_mm:.2f}", f"{h.y_mm:.2f}"])
        if not self._side_b:
            self._dvc_side_b.AppendItem(["(none)", "", "", ""])

    def _build_fp_entries(self) -> None:
        """Rebuild _fp_entries from the board and update the list control."""
        from enclosure_template import get_footprint_entries
        full = load_panel_config(self._board_path or "", self.plugin_dir)
        raw = get_footprint_entries(self.board, full)
        self._fp_entries = []
        self._fp_originals = {}
        for e in raw:
            fp_id = e["fp_id"]
            orig_cfg = self._global_config.footprints.get(fp_id)
            fe = _FpEntry(
                fp_id=fp_id,
                reference=e["reference"],
                label=e["label"],
                hole_dia=e["hole_dia"],
                offset_x=e["offset_x"],
                offset_y=e["offset_y"],
                ref_enc_x=e["ref_enc_x"],
                ref_enc_y=e["ref_enc_y"],
                orientation_rad=e.get("orientation_rad", 0.0),
                use_pad_centroid=e.get("use_pad_centroid",
                                       orig_cfg.use_pad_centroid if orig_cfg else False),
            )
            self._fp_entries.append(fe)
            self._fp_originals[fp_id] = {
                "hole_dia": e["hole_dia"],
                "offset_x": e["offset_x"],
                "offset_y": e["offset_y"],
            }
        self._fp_selected = None
        self._refresh_fp_list()

    def _refresh_fp_list(self) -> None:
        self._dvc_auto.DeleteAllItems()
        for e in self._fp_entries:
            label = f"[excl] {e.label}" if e.excluded else e.label
            x_str = y_str = ox_str = oy_str = ""
            if not e.excluded:
                x_str  = f"{e.enc_x:.2f}"
                y_str  = f"{e.enc_y:.2f}"
                ox_str = f"{e.offset_x:+.2f}"
                oy_str = f"{e.offset_y:+.2f}"
            self._dvc_auto.AppendItem([label, f"{e.hole_dia:.2f}", x_str, y_str, ox_str, oy_str])
        if not self._fp_entries:
            self._dvc_auto.AppendItem(["(none detected)", "", "", "", "", ""])

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

    def _on_preset_changed(self, event: Any) -> None:
        preset = _PRESET_CHOICES[self._cho_preset.GetSelection()]
        if preset == "Custom" or preset not in ENCLOSURE_PRESETS:
            return
        pdata = ENCLOSURE_PRESETS[preset]
        self._updating = True
        self._txt_enc_w.SetValue(f"{pdata['width']:.1f}")
        self._txt_enc_h.SetValue(f"{pdata['height']:.1f}")
        self._txt_enc_d.SetValue(f"{pdata['depth']:.1f}")
        self._updating = False
        self._refresh_layout_choices()
        if self._use_webview:
            self._on_preview(None)

    def _on_apply_layout(self, event: Any) -> None:
        preset = self._current_preset()
        if not preset or preset not in ENCLOSURE_PRESETS:
            return
        layouts = ENCLOSURE_PRESETS[preset].get("side_b_layouts", [])
        if not layouts:
            return
        idx = self._cho_layout.GetSelection()
        if idx < 0 or idx >= len(layouts):
            return
        layout = layouts[idx]
        if wx.MessageBox(
            f"Replace Side B holes with layout \"{layout['name']}\"?\n"
            "This will overwrite any existing top-face holes.",
            "Apply Layout",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
        ) != wx.YES:
            return
        from panel_config import _side_b_hole_from_dict
        self._side_b = [_side_b_hole_from_dict(h) for h in layout["holes"]]
        self._refresh_side_b_list()

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
        if self._use_webview:
            self._on_preview(None)

    def _on_delete(self, event: Any) -> None:
        if self._selected is None:
            return
        del self._rows[self._selected]
        self._selected = None
        self._refresh_list()
        for ctrl in (self._txt_label, self._txt_dia, self._txt_x, self._txt_y):
            ctrl.Enable(False)
        if self._use_webview:
            self._on_preview(None)

    def _on_manage_rules(self, event: Any) -> None:
        try:
            from footprint_rules_dialog import FootprintRulesDialog
            dlg = FootprintRulesDialog(self, self.board, self.plugin_dir)
            dlg.ShowModal()
            dlg.Destroy()
            # Rules may have changed — rebuild fp entries and refresh preview.
            self._build_fp_entries()
            if self._use_webview:
                self._on_preview(None)
        except Exception:
            import traceback
            wx.MessageBox(traceback.format_exc(), "Rules Editor Error", wx.OK | wx.ICON_ERROR)

    def _on_fp_selection(self, event: Any) -> None:
        row = self._dvc_auto.GetSelectedRow()
        if row < 0 or row >= len(self._fp_entries):
            self._fp_selected = None
            for ctrl in (self._txt_fp_dia, self._txt_fp_ox, self._txt_fp_oy):
                ctrl.Enable(False)
            self._btn_fp_exclude.Enable(False)
            return
        self._fp_selected = row
        e = self._fp_entries[row]
        self._updating = True
        self._txt_fp_dia.SetValue(f"{e.hole_dia:.2f}")
        self._txt_fp_ox.SetValue(f"{e.offset_x:.2f}")
        self._txt_fp_oy.SetValue(f"{e.offset_y:.2f}")
        self._updating = False
        editable = not e.excluded
        for ctrl in (self._txt_fp_dia, self._txt_fp_ox, self._txt_fp_oy):
            ctrl.Enable(editable)
        self._btn_fp_exclude.SetLabel("Re-enable Hole" if e.excluded else "Exclude from Holes")
        self._btn_fp_exclude.Enable(True)
        if self._use_webview:
            self._on_preview(None)

    def _on_fp_edit(self, event: Any) -> None:
        if self._updating or self._fp_selected is None:
            return
        row = self._fp_selected
        e = self._fp_entries[row]
        try:
            new_dia = float(self._txt_fp_dia.GetValue())
            new_ox = float(self._txt_fp_ox.GetValue())
            new_oy = float(self._txt_fp_oy.GetValue())
        except ValueError:
            return
        e.hole_dia = new_dia
        e.offset_x = new_ox
        e.offset_y = new_oy
        self._dvc_auto.SetTextValue(f"{e.hole_dia:.2f}",   row, 1)
        self._dvc_auto.SetTextValue(f"{e.enc_x:.2f}",      row, 2)
        self._dvc_auto.SetTextValue(f"{e.enc_y:.2f}",      row, 3)
        self._dvc_auto.SetTextValue(f"{e.offset_x:+.2f}",  row, 4)
        self._dvc_auto.SetTextValue(f"{e.offset_y:+.2f}",  row, 5)
        if self._fp_preview_timer is not None:
            self._fp_preview_timer.Stop()
        self._fp_preview_timer = wx.CallLater(350, self._on_preview, None)

    def _on_fp_exclude(self, event: Any) -> None:
        if self._fp_selected is None:
            return
        e = self._fp_entries[self._fp_selected]
        e.excluded = not e.excluded
        self._btn_fp_exclude.SetLabel("Re-enable Hole" if e.excluded else "Exclude from Holes")
        editable = not e.excluded
        for ctrl in (self._txt_fp_dia, self._txt_fp_ox, self._txt_fp_oy):
            ctrl.Enable(editable)
        # Update list row label
        row = self._fp_selected
        label = f"[excl] {e.label}" if e.excluded else e.label
        self._dvc_auto.SetTextValue(label, row, 0)
        for col in (2, 3, 4, 5):
            self._dvc_auto.SetTextValue("" if e.excluded else self._dvc_auto.GetTextValue(row, col), row, col)
        # Refresh the row cleanly
        self._dvc_auto.SetTextValue(label, row, 0)
        if not e.excluded:
            self._dvc_auto.SetTextValue(f"{e.enc_x:.2f}", row, 2)
            self._dvc_auto.SetTextValue(f"{e.enc_y:.2f}", row, 3)
            self._dvc_auto.SetTextValue(f"{e.offset_x:+.2f}", row, 4)
            self._dvc_auto.SetTextValue(f"{e.offset_y:+.2f}", row, 5)
        else:
            for col in (2, 3, 4, 5):
                self._dvc_auto.SetTextValue("", row, col)
        if self._use_webview:
            self._on_preview(None)

    def _current_preset(self) -> Optional[str]:
        """Return the selected preset name, or None for Custom."""
        name = _PRESET_CHOICES[self._cho_preset.GetSelection()]
        return name if name != "Custom" else None

    def _build_config(self) -> PanelConfig:
        """Build a PanelConfig from current dialog state (enclosure + fixed holes)."""
        try:
            enc = EnclosureConfig(
                width=float(self._txt_enc_w.GetValue()),
                height=float(self._txt_enc_h.GetValue()),
                depth=float(self._txt_enc_d.GetValue()),
                preset=self._current_preset(),
            )
        except ValueError:
            enc = self._enclosure
        return PanelConfig(enclosure=enc, footprints={}, fixed_holes=list(self._rows))

    def _generate_preview_pdf(self) -> Optional[str]:
        """Generate enclosure PDF to a temp file and return its path, or None on error."""
        from enclosure_template import generate_enclosure_pdf
        config = self._build_config()
        full = load_panel_config(self._board_path or "", self.plugin_dir)
        # Apply current in-dialog fp_entry overrides on top of the loaded footprints.
        merged_fps = dict(full.footprints)
        for e in self._fp_entries:
            if e.excluded:
                merged_fps.pop(e.fp_id, None)  # suppress hole for excluded footprints
            elif e.fp_id in merged_fps:
                orig = merged_fps[e.fp_id]
                merged_fps[e.fp_id] = FootprintHoleConfig(
                    hole_dia=e.hole_dia,
                    offset_x=e.offset_x,
                    offset_y=e.offset_y,
                    label=orig.label,
                    use_pad_centroid=orig.use_pad_centroid,
                )
            else:
                # Auto-detected entry (e.g. back-copper LED) not in any config file yet.
                # Add it so the preview reflects in-dialog edits.
                merged_fps[e.fp_id] = FootprintHoleConfig(
                    hole_dia=e.hole_dia,
                    offset_x=e.offset_x,
                    offset_y=e.offset_y,
                    use_pad_centroid=e.use_pad_centroid,
                )
        config = PanelConfig(
            enclosure=config.enclosure,
            footprints=merged_fps,
            fixed_holes=config.fixed_holes,
            side_b=full.side_b,
        )
        highlight_refs: Optional[Set[str]] = None
        if self._fp_selected is not None and self._fp_selected < len(self._fp_entries):
            highlight_refs = {self._fp_entries[self._fp_selected].reference}
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
                face_only=True,
                highlight_refs=highlight_refs,
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

    def _on_reset_template(self, event: Any) -> None:
        if wx.MessageBox(
            "Reset enclosure and fixed holes to the global template?\n"
            "Your current edits will be lost.",
            "Reset to Template",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
        ) != wx.YES:
            return
        self._enclosure = self._global_config.enclosure
        self._rows = list(self._global_config.fixed_holes)
        self._side_b = list(self._global_config.side_b)
        self._selected = None
        self._updating = True
        preset_idx = (
            _PRESET_CHOICES.index(self._enclosure.preset)
            if self._enclosure.preset in _PRESET_CHOICES
            else 0
        )
        self._cho_preset.SetSelection(preset_idx)
        self._txt_enc_w.SetValue(f"{self._enclosure.width:.1f}")
        self._txt_enc_h.SetValue(f"{self._enclosure.height:.1f}")
        self._txt_enc_d.SetValue(f"{self._enclosure.depth:.1f}")
        self._updating = False
        self._refresh_layout_choices()
        self._refresh_list()
        self._refresh_side_b_list()
        for ctrl in (self._txt_label, self._txt_dia, self._txt_x, self._txt_y):
            ctrl.Enable(False)
        if self._use_webview:
            self._on_preview(None)

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

        # Load existing project JSON to preserve any footprint overrides the user
        # may have set by hand; replace enclosure and fixed_holes entirely.
        existing: dict = {}
        if os.path.exists(self._project_json):
            try:
                with open(self._project_json) as fh:
                    existing = json.load(fh)
            except Exception:
                pass

        enc_dict: dict = {"width": enc_w, "height": enc_h, "depth": enc_d}
        preset = self._current_preset()
        if preset:
            enc_dict["preset"] = preset
        existing["enclosure"] = enc_dict
        existing["fixed_holes"] = [
            {"label": h.label, "dia": h.dia, "x": h.x, "y": h.y}
            for h in self._rows
        ]
        existing["side_b"] = [
            {"label": h.label, "diameter_mm": h.diameter_mm, "x_mm": h.x_mm, "y_mm": h.y_mm}
            for h in self._side_b
        ]
        # Write per-project footprint offset overrides: only entries that changed
        # from what was loaded (either from the global config or a prior project override).
        fp_overrides: dict = existing.get("footprints", {}) or {}
        for e in self._fp_entries:
            if e.excluded:
                fp_overrides[e.fp_id] = None   # null = suppress this footprint's hole
                continue
            # Remove any previously-written null override if the user re-enabled it.
            if fp_overrides.get(e.fp_id) is None:
                fp_overrides.pop(e.fp_id, None)
            orig = self._fp_originals.get(e.fp_id)
            if orig is None:
                continue
            if (e.hole_dia != orig["hole_dia"]
                    or e.offset_x != orig["offset_x"]
                    or e.offset_y != orig["offset_y"]):
                entry: dict = {
                    "hole_dia": e.hole_dia,
                    "offset_x": e.offset_x,
                    "offset_y": e.offset_y,
                }
                if e.use_pad_centroid:
                    entry["use_pad_centroid"] = True
                fp_overrides[e.fp_id] = entry
        if fp_overrides:
            existing["footprints"] = fp_overrides
        # Remove the now-obsolete remove_fixed_holes key if present from an old file.
        existing.pop("remove_fixed_holes", None)

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
