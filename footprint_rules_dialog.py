"""Footprint hole rules editor — add/edit global panel_config.json footprint rules.

Scans the current board for footprints that have a Control field but no matching
entry in the global rules, and presents them as candidates to add.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import wx
import wx.dataview as dv

from footprint_utils import get_board_path, get_field, get_fp_id, safe_get_footprints
from panel_config import ENCLOSURE_PRESETS, FootprintHoleConfig, load_panel_config

_LED_RE = re.compile(r"^(D|LED)\d", re.IGNORECASE)
_LED_LIB_RE = re.compile(r"^(LED_SMD|LED_THT|Diode_SMD|Diode_THT)", re.IGNORECASE)

# Columns for the candidates list
_CC_ID    = 0
_CC_REFS  = 1
_CC_LABEL = 2

# Columns for the existing-rules list
_RC_ID     = 0
_RC_DIA    = 1
_RC_OFF_X  = 2
_RC_OFF_Y  = 3
_RC_LABEL  = 4
_RC_CENTRD = 5


@dataclass
class _Candidate:
    fp_id: str
    refs: List[str]
    example_label: str


class FootprintRulesDialog(wx.Dialog):
    """Scan board for unrecognized footprints and edit the global panel_config.json."""

    def __init__(self, parent, board, plugin_dir: str) -> None:
        super().__init__(parent, title="Edit Footprint Hole Rules", size=(900, 620),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._board = board
        self._board_path = get_board_path(board)
        self._plugin_dir = plugin_dir
        self._plugin_json = os.path.join(plugin_dir, "panel_config.json")

        # State
        self._candidates: List[_Candidate] = []
        self._rule_keys: List[str] = []
        self._rules: Dict[str, FootprintHoleConfig] = {}
        self._sel_candidate: Optional[int] = None  # index into _candidates
        self._sel_rule: Optional[int] = None        # index into _rule_keys
        self._updating = False
        self._preview_path: Optional[str] = None

        self._use_webview = self._check_webview()
        self._load_rules()
        self._scan_candidates()
        self._build_ui()
        self._refresh_candidates()
        self._refresh_rules()

    # ── WebView ───────────────────────────────────────────────────────────────

    @staticmethod
    def _check_webview() -> bool:
        try:
            import wx.html2  # noqa: F401
            return True
        except Exception:
            return False

    # ── I/O ──────────────────────────────────────────────────────────────────

    def _load_rules(self) -> None:
        try:
            with open(self._plugin_json) as fh:
                data = json.load(fh)
            fps = data.get("footprints", {})
            self._rule_keys = [k for k in fps if fps[k] is not None]
            self._rules = {}
            for k in self._rule_keys:
                d = fps[k]
                self._rules[k] = FootprintHoleConfig(
                    hole_dia=float(d.get("hole_dia", 8.0)),
                    offset_x=float(d.get("offset_x", 0.0)),
                    offset_y=float(d.get("offset_y", 0.0)),
                    label=d.get("label") or None,
                    use_pad_centroid=bool(d.get("use_pad_centroid", False)),
                )
        except FileNotFoundError:
            self._rule_keys = []
            self._rules = {}
        except Exception as exc:
            wx.MessageBox(f"Could not load panel_config.json:\n{exc}",
                          "Load Error", wx.OK | wx.ICON_WARNING)

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
                for k in self._rule_keys
            }
            with open(self._plugin_json, "w") as fh:
                json.dump(existing, fh, indent=2)
            return True
        except Exception as exc:
            wx.MessageBox(f"Could not save panel_config.json:\n{exc}",
                          "Save Error", wx.OK | wx.ICON_ERROR)
            return False

    # ── Board scan ────────────────────────────────────────────────────────────

    def _scan_candidates(self) -> None:
        """Find footprints with a Control field that have no global rule."""
        known_ids = set(self._rule_keys)
        seen: Dict[str, _Candidate] = {}
        for fp in safe_get_footprints(self._board):
            ref = fp.reference_field.text.value
            if ref.startswith("~") or ref in ("REF**", ""):
                continue
            if _LED_RE.match(ref):
                continue
            try:
                if _LED_LIB_RE.match(fp.definition.id.library):
                    continue
            except Exception:
                pass
            label = get_field(fp, "Control")
            if not label:
                continue
            fp_id = get_fp_id(fp)
            if fp_id in known_ids:
                continue
            if fp_id not in seen:
                seen[fp_id] = _Candidate(fp_id=fp_id, refs=[ref], example_label=label)
            else:
                seen[fp_id].refs.append(ref)
        self._candidates = list(seen.values())
        self._candidates.sort(key=lambda c: c.fp_id)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        root = wx.BoxSizer(wx.HORIZONTAL)

        # ── Left column ───────────────────────────────────────────
        left = wx.BoxSizer(wx.VERTICAL)

        # Candidates
        cand_label = wx.StaticText(panel, label="Footprints on this board with no hole rule:")
        cand_label.SetFont(cand_label.GetFont().Bold())
        left.Add(cand_label, flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=8)

        self._dvc_cand = dv.DataViewListCtrl(
            panel, style=dv.DV_SINGLE | dv.DV_ROW_LINES | dv.DV_NO_HEADER)
        self._dvc_cand.AppendTextColumn("Footprint ID", width=280, mode=dv.DATAVIEW_CELL_INERT)
        self._dvc_cand.AppendTextColumn("Refs",         width=100, mode=dv.DATAVIEW_CELL_INERT)
        self._dvc_cand.AppendTextColumn("Control",      width=130, mode=dv.DATAVIEW_CELL_INERT)
        self._dvc_cand.Bind(dv.EVT_DATAVIEW_SELECTION_CHANGED, self._on_cand_selected)
        left.Add(self._dvc_cand, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        if not self._candidates:
            left.Add(wx.StaticText(panel, label="  ✓ All board footprints have rules."),
                     flag=wx.LEFT | wx.BOTTOM, border=8)

        # Edit fields (shared for both lists)
        edit_box = wx.StaticBox(panel, label="Rule settings")
        edit_sizer = wx.StaticBoxSizer(edit_box, wx.VERTICAL)
        grid = wx.FlexGridSizer(cols=6, vgap=5, hgap=8)

        def lbl(t: str) -> wx.StaticText:
            return wx.StaticText(panel, label=t)

        grid.Add(lbl("Hole dia (mm):"), flag=wx.ALIGN_CENTER_VERTICAL)
        self._txt_dia = wx.TextCtrl(panel, value="8.00", size=(62, -1))
        grid.Add(self._txt_dia, flag=wx.ALIGN_CENTER_VERTICAL)

        grid.Add(lbl("Offset X (mm):"), flag=wx.ALIGN_CENTER_VERTICAL)
        self._txt_off_x = wx.TextCtrl(panel, value="0.00", size=(62, -1))
        grid.Add(self._txt_off_x, flag=wx.ALIGN_CENTER_VERTICAL)

        grid.Add(lbl("Offset Y (mm):"), flag=wx.ALIGN_CENTER_VERTICAL)
        self._txt_off_y = wx.TextCtrl(panel, value="0.00", size=(62, -1))
        grid.Add(self._txt_off_y, flag=wx.ALIGN_CENTER_VERTICAL)

        grid.Add(lbl("Label (optional):"), flag=wx.ALIGN_CENTER_VERTICAL)
        self._txt_label = wx.TextCtrl(panel, size=(110, -1))
        grid.Add(self._txt_label, flag=wx.ALIGN_CENTER_VERTICAL)

        grid.Add(lbl("Pad centroid:"), flag=wx.ALIGN_CENTER_VERTICAL)
        self._chk_centroid = wx.CheckBox(panel)
        grid.Add(self._chk_centroid, flag=wx.ALIGN_CENTER_VERTICAL)

        # spacer so the 6-col grid lines up neatly with 3 pairs
        grid.AddStretchSpacer()
        grid.AddStretchSpacer()

        edit_sizer.Add(grid, flag=wx.EXPAND | wx.ALL, border=6)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self._btn_add_rule = wx.Button(panel, label="Add as Global Rule ↓")
        self._btn_add_rule.Bind(wx.EVT_BUTTON, self._on_add_rule)
        self._btn_add_rule.Enable(False)
        btn_row.Add(self._btn_add_rule, flag=wx.RIGHT, border=8)
        if self._use_webview:
            btn_preview = wx.Button(panel, label="Refresh Preview")
        else:
            btn_preview = wx.Button(panel, label="Preview PDF")
        btn_preview.Bind(wx.EVT_BUTTON, self._on_preview)
        btn_row.Add(btn_preview)
        edit_sizer.Add(btn_row, flag=wx.LEFT | wx.BOTTOM, border=6)

        left.Add(edit_sizer, flag=wx.EXPAND | wx.ALL, border=8)

        for ctrl in (self._txt_dia, self._txt_off_x, self._txt_off_y,
                     self._txt_label, self._chk_centroid):
            if isinstance(ctrl, wx.TextCtrl):
                ctrl.Bind(wx.EVT_TEXT, self._on_edit)
            else:
                ctrl.Bind(wx.EVT_CHECKBOX, self._on_edit)
            ctrl.Enable(False)

        # Existing rules
        rules_label = wx.StaticText(panel, label="Existing global rules:")
        rules_label.SetFont(rules_label.GetFont().Bold())
        left.Add(rules_label, flag=wx.LEFT | wx.BOTTOM, border=8)

        self._dvc_rules = dv.DataViewListCtrl(
            panel, style=dv.DV_SINGLE | dv.DV_ROW_LINES | dv.DV_NO_HEADER)
        self._dvc_rules.AppendTextColumn("Footprint ID",  width=240, mode=dv.DATAVIEW_CELL_INERT)
        self._dvc_rules.AppendTextColumn("Hole dia",      width=65,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc_rules.AppendTextColumn("Offset X",      width=65,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc_rules.AppendTextColumn("Offset Y",      width=65,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc_rules.AppendTextColumn("Label",         width=100, mode=dv.DATAVIEW_CELL_INERT)
        self._dvc_rules.AppendTextColumn("Centroid",      width=60,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc_rules.Bind(dv.EVT_DATAVIEW_SELECTION_CHANGED, self._on_rule_selected)
        left.Add(self._dvc_rules, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        del_row = wx.BoxSizer(wx.HORIZONTAL)
        self._btn_del = wx.Button(panel, label="Delete Rule")
        self._btn_del.Bind(wx.EVT_BUTTON, self._on_delete_rule)
        self._btn_del.Enable(False)
        del_row.Add(self._btn_del)
        left.Add(del_row, flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=8)

        # Apply / Cancel
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        btn_apply  = wx.Button(panel, label="Apply")
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancel")
        btn_apply.SetDefault()
        btn_apply.Bind(wx.EVT_BUTTON, self._on_apply)
        btn_sizer.Add(btn_apply, flag=wx.RIGHT, border=6)
        btn_sizer.Add(btn_cancel)
        left.Add(btn_sizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        root.Add(left, proportion=1, flag=wx.EXPAND)

        # ── Right column: WebView preview ─────────────────────────
        if self._use_webview:
            self._webview = wx.html2.WebView.New(panel, size=(300, -1))
            root.Add(self._webview, proportion=0,
                     flag=wx.EXPAND | wx.TOP | wx.RIGHT | wx.BOTTOM, border=8)

        panel.SetSizer(root)
        self.Layout()

    # ── List refresh ──────────────────────────────────────────────────────────

    def _refresh_candidates(self) -> None:
        self._dvc_cand.DeleteAllItems()
        for c in self._candidates:
            self._dvc_cand.AppendItem([
                c.fp_id,
                ", ".join(c.refs[:4]) + ("…" if len(c.refs) > 4 else ""),
                c.example_label,
            ])

    def _refresh_rules(self) -> None:
        self._dvc_rules.DeleteAllItems()
        for k in self._rule_keys:
            cfg = self._rules[k]
            self._dvc_rules.AppendItem([
                k,
                f"{cfg.hole_dia:.2f}",
                f"{cfg.offset_x:+.2f}",
                f"{cfg.offset_y:+.2f}",
                cfg.label or "",
                "yes" if cfg.use_pad_centroid else "",
            ])

    def _update_rule_row(self, row: int) -> None:
        cfg = self._rules[self._rule_keys[row]]
        self._dvc_rules.SetTextValue(self._rule_keys[row],         row, _RC_ID)
        self._dvc_rules.SetTextValue(f"{cfg.hole_dia:.2f}",        row, _RC_DIA)
        self._dvc_rules.SetTextValue(f"{cfg.offset_x:+.2f}",       row, _RC_OFF_X)
        self._dvc_rules.SetTextValue(f"{cfg.offset_y:+.2f}",       row, _RC_OFF_Y)
        self._dvc_rules.SetTextValue(cfg.label or "",               row, _RC_LABEL)
        self._dvc_rules.SetTextValue("yes" if cfg.use_pad_centroid else "", row, _RC_CENTRD)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _cfg_from_fields(self) -> Optional[FootprintHoleConfig]:
        try:
            return FootprintHoleConfig(
                hole_dia=float(self._txt_dia.GetValue()),
                offset_x=float(self._txt_off_x.GetValue()),
                offset_y=float(self._txt_off_y.GetValue()),
                label=self._txt_label.GetValue().strip() or None,
                use_pad_centroid=self._chk_centroid.GetValue(),
            )
        except ValueError:
            return None

    def _fill_fields(self, cfg: FootprintHoleConfig) -> None:
        self._updating = True
        self._txt_dia.SetValue(f"{cfg.hole_dia:.2f}")
        self._txt_off_x.SetValue(f"{cfg.offset_x:.2f}")
        self._txt_off_y.SetValue(f"{cfg.offset_y:.2f}")
        self._txt_label.SetValue(cfg.label or "")
        self._chk_centroid.SetValue(cfg.use_pad_centroid)
        self._updating = False

    def _enable_edit_fields(self, enabled: bool) -> None:
        for ctrl in (self._txt_dia, self._txt_off_x, self._txt_off_y,
                     self._txt_label, self._chk_centroid):
            ctrl.Enable(enabled)

    def _generate_preview_pdf(self, fp_id: str, cfg: FootprintHoleConfig) -> Optional[str]:
        from enclosure_template import generate_enclosure_pdf
        full = load_panel_config(self._board_path or "", self._plugin_dir)
        from panel_config import PanelConfig
        preview_cfg = PanelConfig(
            enclosure=full.enclosure,
            footprints={fp_id: cfg},
            fixed_holes=full.fixed_holes,
            side_b=full.side_b,
        )
        try:
            tf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tf.close()
            generate_enclosure_pdf(
                board=self._board,
                config=preview_cfg,
                project_name="Preview",
                author="",
                total_pages=1,
                page_num=1,
                out_path=tf.name,
                face_only=True,
            )
            return tf.name
        except Exception as exc:
            wx.MessageBox(f"Preview failed:\n{exc}", "Preview Error", wx.OK | wx.ICON_WARNING)
            return None

    def _show_preview(self, fp_id: str, cfg: FootprintHoleConfig) -> None:
        path = self._generate_preview_pdf(fp_id, cfg)
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
            import subprocess, sys
            if sys.platform == "darwin":
                subprocess.Popen(["open", path])
            elif sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", path])

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_cand_selected(self, event: Any) -> None:
        row = self._dvc_cand.GetSelectedRow()
        if row < 0 or row >= len(self._candidates):
            self._sel_candidate = None
            self._btn_add_rule.Enable(False)
            self._enable_edit_fields(False)
            return
        self._sel_candidate = row
        self._sel_rule = None
        self._dvc_rules.UnselectAll()
        self._btn_add_rule.Enable(True)
        self._btn_del.Enable(False)
        # Default fields for a new rule
        self._fill_fields(FootprintHoleConfig(
            hole_dia=8.0, offset_x=0.0, offset_y=0.0,
            label=self._candidates[row].example_label,
        ))
        self._enable_edit_fields(True)

    def _on_rule_selected(self, event: Any) -> None:
        row = self._dvc_rules.GetSelectedRow()
        if row < 0 or row >= len(self._rule_keys):
            self._sel_rule = None
            self._btn_del.Enable(False)
            self._enable_edit_fields(False)
            return
        self._sel_rule = row
        self._sel_candidate = None
        self._dvc_cand.UnselectAll()
        self._btn_add_rule.Enable(False)
        self._btn_del.Enable(True)
        self._fill_fields(self._rules[self._rule_keys[row]])
        self._enable_edit_fields(True)

    def _on_edit(self, event: Any) -> None:
        if self._updating:
            return
        cfg = self._cfg_from_fields()
        if cfg is None:
            return
        # Live-update the existing rule if one is selected
        if self._sel_rule is not None:
            self._rules[self._rule_keys[self._sel_rule]] = cfg
            self._update_rule_row(self._sel_rule)

    def _on_add_rule(self, event: Any) -> None:
        if self._sel_candidate is None:
            return
        cfg = self._cfg_from_fields()
        if cfg is None:
            wx.MessageBox("Please enter a valid hole diameter.",
                          "Invalid Input", wx.OK | wx.ICON_WARNING)
            return
        cand = self._candidates[self._sel_candidate]
        fp_id = cand.fp_id
        if fp_id in self._rules:
            # Already exists (shouldn't happen, but be safe)
            self._rules[fp_id] = cfg
            row = self._rule_keys.index(fp_id)
            self._update_rule_row(row)
        else:
            self._rule_keys.append(fp_id)
            self._rules[fp_id] = cfg
            self._dvc_rules.AppendItem([
                fp_id,
                f"{cfg.hole_dia:.2f}",
                f"{cfg.offset_x:+.2f}",
                f"{cfg.offset_y:+.2f}",
                cfg.label or "",
                "yes" if cfg.use_pad_centroid else "",
            ])
        # Remove from candidates
        del self._candidates[self._sel_candidate]
        self._sel_candidate = None
        self._btn_add_rule.Enable(False)
        self._enable_edit_fields(False)
        self._refresh_candidates()

    def _on_delete_rule(self, event: Any) -> None:
        if self._sel_rule is None:
            return
        fp_id = self._rule_keys[self._sel_rule]
        del self._rules[fp_id]
        del self._rule_keys[self._sel_rule]
        self._sel_rule = None
        self._btn_del.Enable(False)
        self._enable_edit_fields(False)
        self._refresh_rules()
        # Re-scan: the deleted footprint might now appear as a candidate if it's on the board
        self._scan_candidates()
        self._refresh_candidates()

    def _on_preview(self, event: Any) -> None:
        cfg = self._cfg_from_fields()
        if cfg is None:
            return
        if self._sel_candidate is not None:
            fp_id = self._candidates[self._sel_candidate].fp_id
        elif self._sel_rule is not None:
            fp_id = self._rule_keys[self._sel_rule]
        else:
            return
        self._show_preview(fp_id, cfg)

    def _on_apply(self, event: Any) -> None:
        if self._save_rules():
            self.EndModal(wx.ID_OK)

    def Destroy(self) -> bool:
        if self._preview_path:
            try:
                os.unlink(self._preview_path)
            except OSError:
                pass
        return super().Destroy()
