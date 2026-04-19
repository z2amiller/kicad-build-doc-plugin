"""Footprint hole rules editor — edit the global panel_config.json footprints table."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import wx
import wx.dataview as dv

from panel_config import FootprintHoleConfig

COL_FP_ID  = 0
COL_DIA    = 1
COL_OFF_X  = 2
COL_OFF_Y  = 3
COL_LABEL  = 4
COL_CENTRD = 5


class FootprintRulesDialog(wx.Dialog):
    """Edit the footprint → hole-config mapping in the global panel_config.json."""

    def __init__(self, parent, plugin_dir: str) -> None:
        super().__init__(parent, title="Edit Footprint Hole Rules", size=(780, 520),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._plugin_dir = plugin_dir
        self._plugin_json = os.path.join(plugin_dir, "panel_config.json")

        self._keys: List[str] = []
        self._rules: Dict[str, FootprintHoleConfig] = {}
        self._selected: Optional[int] = None
        self._updating = False

        self._load_rules()
        self._build_ui()
        self._refresh_list()

    # ── I/O ──────────────────────────────────────────────────────────────────

    def _load_rules(self) -> None:
        try:
            with open(self._plugin_json) as fh:
                data = json.load(fh)
            fps = data.get("footprints", {})
            self._keys = [k for k in fps if fps[k] is not None]
            self._rules = {}
            for k in self._keys:
                d = fps[k]
                self._rules[k] = FootprintHoleConfig(
                    hole_dia=float(d.get("hole_dia", 8.0)),
                    offset_x=float(d.get("offset_x", 0.0)),
                    offset_y=float(d.get("offset_y", 0.0)),
                    label=d.get("label") or None,
                    use_pad_centroid=bool(d.get("use_pad_centroid", False)),
                )
        except FileNotFoundError:
            self._keys = []
            self._rules = {}
        except Exception as exc:
            wx.MessageBox(f"Could not load panel_config.json:\n{exc}",
                          "Load Error", wx.OK | wx.ICON_WARNING)
            self._keys = []
            self._rules = {}

    def _save_rules(self) -> bool:
        try:
            existing: dict = {}
            if os.path.exists(self._plugin_json):
                with open(self._plugin_json) as fh:
                    existing = json.load(fh)
            existing["footprints"] = {
                k: {
                    "hole_dia": self._rules[k].hole_dia,
                    "offset_x": self._rules[k].offset_x,
                    "offset_y": self._rules[k].offset_y,
                    **({"label": self._rules[k].label} if self._rules[k].label else {}),
                    **({"use_pad_centroid": True} if self._rules[k].use_pad_centroid else {}),
                }
                for k in self._keys
            }
            with open(self._plugin_json, "w") as fh:
                json.dump(existing, fh, indent=2)
            return True
        except Exception as exc:
            wx.MessageBox(f"Could not save panel_config.json:\n{exc}",
                          "Save Error", wx.OK | wx.ICON_ERROR)
            return False

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        root = wx.BoxSizer(wx.VERTICAL)

        # ── Hint ─────────────────────────────────────────────────────────────
        hint = wx.StaticText(
            panel,
            label="These rules apply to all projects. The footprint ID must match KiCad exactly (Library:Name).",
        )
        hint.SetForegroundColour(wx.Colour(80, 80, 80))
        hint.SetFont(hint.GetFont().Scaled(0.9))
        root.Add(hint, flag=wx.EXPAND | wx.ALL, border=10)

        # ── List ─────────────────────────────────────────────────────────────
        self._dvc = dv.DataViewListCtrl(panel, style=dv.DV_SINGLE | dv.DV_ROW_LINES | dv.DV_NO_HEADER)
        self._dvc.AppendTextColumn("Footprint ID",   width=260, mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("Hole Dia (mm)",  width=90,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("Offset X (mm)",  width=90,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("Offset Y (mm)",  width=90,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("Label",          width=110, mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("Pad centroid",   width=80,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.Bind(dv.EVT_DATAVIEW_SELECTION_CHANGED, self._on_selection)
        root.Add(self._dvc, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)

        # ── Add / Delete ──────────────────────────────────────────────────────
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        btn_add = wx.Button(panel, label="Add Rule")
        btn_del = wx.Button(panel, label="Delete")
        btn_add.Bind(wx.EVT_BUTTON, self._on_add)
        btn_del.Bind(wx.EVT_BUTTON, self._on_delete)
        btn_row.Add(btn_add, flag=wx.RIGHT, border=6)
        btn_row.Add(btn_del)
        root.Add(btn_row, flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=10)

        # ── Edit fields ───────────────────────────────────────────────────────
        edit_box = wx.StaticBox(panel, label="Edit selected rule")
        edit_sizer = wx.StaticBoxSizer(edit_box, wx.VERTICAL)
        grid = wx.FlexGridSizer(cols=4, vgap=6, hgap=10)
        grid.AddGrowableCol(1, 2)
        grid.AddGrowableCol(3, 1)

        def lbl(text: str) -> wx.StaticText:
            return wx.StaticText(panel, label=text)

        grid.Add(lbl("Footprint ID:"), flag=wx.ALIGN_CENTER_VERTICAL)
        self._txt_fp_id = wx.TextCtrl(panel)
        grid.Add(self._txt_fp_id, flag=wx.EXPAND)

        grid.Add(lbl("Hole Dia (mm):"), flag=wx.ALIGN_CENTER_VERTICAL)
        self._txt_dia = wx.TextCtrl(panel, size=(70, -1))
        grid.Add(self._txt_dia)

        grid.Add(lbl("Offset X (mm):"), flag=wx.ALIGN_CENTER_VERTICAL)
        self._txt_off_x = wx.TextCtrl(panel, size=(70, -1))
        grid.Add(self._txt_off_x)

        grid.Add(lbl("Offset Y (mm):"), flag=wx.ALIGN_CENTER_VERTICAL)
        self._txt_off_y = wx.TextCtrl(panel, size=(70, -1))
        grid.Add(self._txt_off_y)

        grid.Add(lbl("Label (optional):"), flag=wx.ALIGN_CENTER_VERTICAL)
        self._txt_label = wx.TextCtrl(panel)
        grid.Add(self._txt_label, flag=wx.EXPAND)

        grid.Add(lbl("Use pad centroid:"), flag=wx.ALIGN_CENTER_VERTICAL)
        self._chk_centroid = wx.CheckBox(panel)
        grid.Add(self._chk_centroid, flag=wx.ALIGN_CENTER_VERTICAL)

        edit_sizer.Add(grid, flag=wx.EXPAND | wx.ALL, border=8)

        hint2 = wx.StaticText(
            panel,
            label="Offset X/Y: mm added after footprint → enclosure transform.  "
                  "Pad centroid: use the geometric centre of the pads instead of the footprint origin.",
        )
        hint2.SetForegroundColour(wx.Colour(100, 100, 100))
        hint2.SetFont(hint2.GetFont().Scaled(0.82))
        edit_sizer.Add(hint2, flag=wx.LEFT | wx.BOTTOM, border=8)

        root.Add(edit_sizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)

        self._edit_controls = [
            self._txt_fp_id, self._txt_dia, self._txt_off_x,
            self._txt_off_y, self._txt_label, self._chk_centroid,
        ]
        for ctrl in self._edit_controls:
            if isinstance(ctrl, wx.TextCtrl):
                ctrl.Bind(wx.EVT_TEXT, self._on_edit)
            else:
                ctrl.Bind(wx.EVT_CHECKBOX, self._on_edit)
            ctrl.Enable(False)

        # ── Apply / Cancel ────────────────────────────────────────────────────
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        btn_apply  = wx.Button(panel, label="Apply")
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancel")
        btn_apply.SetDefault()
        btn_apply.Bind(wx.EVT_BUTTON, self._on_apply)
        btn_sizer.Add(btn_apply, flag=wx.RIGHT, border=6)
        btn_sizer.Add(btn_cancel)
        root.Add(btn_sizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)

        panel.SetSizer(root)
        self.Layout()

    # ── List management ───────────────────────────────────────────────────────

    def _refresh_list(self) -> None:
        self._dvc.DeleteAllItems()
        for k in self._keys:
            cfg = self._rules[k]
            self._dvc.AppendItem([
                k,
                f"{cfg.hole_dia:.2f}",
                f"{cfg.offset_x:+.2f}",
                f"{cfg.offset_y:+.2f}",
                cfg.label or "",
                "yes" if cfg.use_pad_centroid else "",
            ])

    def _fill_edit_fields(self, row: int) -> None:
        k = self._keys[row]
        cfg = self._rules[k]
        self._updating = True
        self._txt_fp_id.SetValue(k)
        self._txt_dia.SetValue(f"{cfg.hole_dia:.2f}")
        self._txt_off_x.SetValue(f"{cfg.offset_x:.2f}")
        self._txt_off_y.SetValue(f"{cfg.offset_y:.2f}")
        self._txt_label.SetValue(cfg.label or "")
        self._chk_centroid.SetValue(cfg.use_pad_centroid)
        self._updating = False

    def _row_from_fields(self) -> Optional[tuple]:
        """Return (fp_id, FootprintHoleConfig) from current edit fields, or None on error."""
        fp_id = self._txt_fp_id.GetValue().strip()
        if not fp_id:
            return None
        try:
            return fp_id, FootprintHoleConfig(
                hole_dia=float(self._txt_dia.GetValue()),
                offset_x=float(self._txt_off_x.GetValue()),
                offset_y=float(self._txt_off_y.GetValue()),
                label=self._txt_label.GetValue().strip() or None,
                use_pad_centroid=self._chk_centroid.GetValue(),
            )
        except ValueError:
            return None

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_selection(self, event: Any) -> None:
        row = self._dvc.GetSelectedRow()
        if row < 0 or row >= len(self._keys):
            self._selected = None
            for ctrl in self._edit_controls:
                ctrl.Enable(False)
            return
        self._selected = row
        self._fill_edit_fields(row)
        for ctrl in self._edit_controls:
            ctrl.Enable(True)

    def _on_edit(self, event: Any) -> None:
        if self._updating or self._selected is None:
            return
        result = self._row_from_fields()
        if result is None:
            return
        new_id, cfg = result
        old_id = self._keys[self._selected]

        if new_id != old_id:
            # Footprint ID changed — rename the key
            if new_id in self._rules:
                return  # duplicate, ignore until user resolves
            del self._rules[old_id]
            self._keys[self._selected] = new_id
            self._rules[new_id] = cfg
        else:
            self._rules[old_id] = cfg

        row = self._selected
        self._dvc.SetTextValue(self._keys[row],               row, COL_FP_ID)
        self._dvc.SetTextValue(f"{cfg.hole_dia:.2f}",         row, COL_DIA)
        self._dvc.SetTextValue(f"{cfg.offset_x:+.2f}",        row, COL_OFF_X)
        self._dvc.SetTextValue(f"{cfg.offset_y:+.2f}",        row, COL_OFF_Y)
        self._dvc.SetTextValue(cfg.label or "",                row, COL_LABEL)
        self._dvc.SetTextValue("yes" if cfg.use_pad_centroid else "", row, COL_CENTRD)

    def _on_add(self, event: Any) -> None:
        new_id = "Library:FootprintName"
        # Make the ID unique if it already exists
        if new_id in self._rules:
            i = 2
            while f"{new_id}_{i}" in self._rules:
                i += 1
            new_id = f"{new_id}_{i}"
        cfg = FootprintHoleConfig(hole_dia=8.0, offset_x=0.0, offset_y=0.0)
        self._keys.append(new_id)
        self._rules[new_id] = cfg
        self._dvc.AppendItem([new_id, "8.00", "+0.00", "+0.00", "", ""])
        new_row = len(self._keys) - 1
        self._dvc.SelectRow(new_row)
        self._on_selection(None)
        self._txt_fp_id.SetFocus()
        self._txt_fp_id.SelectAll()

    def _on_delete(self, event: Any) -> None:
        if self._selected is None:
            return
        old_id = self._keys[self._selected]
        del self._rules[old_id]
        del self._keys[self._selected]
        self._selected = None
        self._refresh_list()
        for ctrl in self._edit_controls:
            ctrl.Enable(False)

    def _on_apply(self, event: Any) -> None:
        if self._save_rules():
            self.EndModal(wx.ID_OK)
