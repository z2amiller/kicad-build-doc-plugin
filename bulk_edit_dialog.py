"""Bulk Description/Notes editor dialog for footprints on the board."""

from __future__ import annotations

from typing import Optional

import wx
import wx.dataview as dv

from footprint_editor import FootprintRow, commit_edits, load_footprints

# Column indices
COL_CHECK = 0
COL_REF = 1
COL_VALUE = 2
COL_TYPE = 3
COL_FP = 4
COL_DESC = 5
COL_NOTES = 6


class BulkEditDialog(wx.Dialog):
    def __init__(self, parent, board):
        super().__init__(
            parent,
            title="Edit Component Descriptions",
            size=(1060, 640),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.board = board
        self._rows: list[FootprintRow] = load_footprints(board)
        self._selected_row: Optional[int] = None
        self._updating = False
        self._build_ui()
        self._populate()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # Instruction text
        info = wx.StaticText(
            panel,
            label=(
                "Select a row to edit its Description and Notes below. "
                "Check rows to enable bulk sync — editing a checked row "
                "updates all other checked rows in the same field."
            ),
        )
        info.Wrap(1020)
        vbox.Add(info, flag=wx.ALL, border=10)

        # DataViewListCtrl — Description and Notes are display-only here
        self._dvc = dv.DataViewListCtrl(
            panel,
            style=dv.DV_ROW_LINES | dv.DV_VERT_RULES,
        )
        self._dvc.AppendToggleColumn("", width=30)
        self._dvc.AppendTextColumn("Ref", width=60, mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("Value", width=100, mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("Type", width=130, mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("Footprint", width=160, mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("Description", width=180, mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("Notes", width=180, mode=dv.DATAVIEW_CELL_INERT)

        self._dvc.Bind(dv.EVT_DATAVIEW_SELECTION_CHANGED, self._on_selection_changed)
        vbox.Add(self._dvc, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)

        # Select All / None buttons
        sel_row = wx.BoxSizer(wx.HORIZONTAL)
        btn_all = wx.Button(panel, label="Select All")
        btn_none = wx.Button(panel, label="Select None")
        btn_all.Bind(wx.EVT_BUTTON, self._on_select_all)
        btn_none.Bind(wx.EVT_BUTTON, self._on_select_none)
        sel_row.Add(btn_all, flag=wx.RIGHT, border=6)
        sel_row.Add(btn_none)
        vbox.Add(sel_row, flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=10)

        # Edit panel
        edit_box = wx.StaticBox(panel, label="Edit Selected Component")
        edit_sizer = wx.StaticBoxSizer(edit_box, wx.VERTICAL)
        edit_grid = wx.FlexGridSizer(cols=2, vgap=6, hgap=8)
        edit_grid.AddGrowableCol(1, 1)

        edit_grid.Add(wx.StaticText(panel, label="Description:"), flag=wx.ALIGN_CENTER_VERTICAL)
        self._txt_desc = wx.TextCtrl(panel)
        edit_grid.Add(self._txt_desc, flag=wx.EXPAND)

        edit_grid.Add(wx.StaticText(panel, label="Notes:"), flag=wx.ALIGN_CENTER_VERTICAL)
        self._txt_notes = wx.TextCtrl(panel)
        edit_grid.Add(self._txt_notes, flag=wx.EXPAND)

        edit_sizer.Add(edit_grid, flag=wx.EXPAND | wx.ALL, border=8)
        vbox.Add(edit_sizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)

        self._txt_desc.Enable(False)
        self._txt_notes.Enable(False)
        self._txt_desc.Bind(wx.EVT_TEXT, self._on_edit_text)
        self._txt_notes.Bind(wx.EVT_TEXT, self._on_edit_text)

        # Apply / Cancel
        btn_sizer = wx.StdDialogButtonSizer()
        btn_apply = wx.Button(panel, label="Apply")
        btn_apply.SetDefault()
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancel")
        btn_sizer.Add(btn_apply, flag=wx.RIGHT, border=8)
        btn_sizer.Add(btn_cancel)
        btn_apply.Bind(wx.EVT_BUTTON, self._on_apply)
        vbox.Add(btn_sizer, flag=wx.ALIGN_RIGHT | wx.ALL, border=10)

        panel.SetSizer(vbox)
        self.Layout()

    def _populate(self) -> None:
        self._dvc.DeleteAllItems()
        for row in self._rows:
            fp_name = row.fp_id.split(":", 1)[-1]
            self._dvc.AppendItem(
                [False, row.ref, row.value, row.fp_type, fp_name, row.description, row.notes]
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _is_checked(self, item_row: int) -> bool:
        return bool(self._dvc.GetToggleValue(item_row, COL_CHECK))

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_selection_changed(self, event: dv.DataViewEvent) -> None:
        item = self._dvc.GetSelection()
        if not item.IsOk():
            self._selected_row = None
            self._txt_desc.Enable(False)
            self._txt_notes.Enable(False)
            return
        row_idx = self._dvc.ItemToRow(item)
        if row_idx < 0:
            return
        self._selected_row = row_idx
        self._updating = True
        self._txt_desc.SetValue(self._rows[row_idx].description)
        self._txt_notes.SetValue(self._rows[row_idx].notes)
        self._txt_desc.Enable(True)
        self._txt_notes.Enable(True)
        self._updating = False

    def _on_edit_text(self, event: wx.CommandEvent) -> None:
        if self._updating or self._selected_row is None:
            return
        row_idx = self._selected_row
        is_desc = event.GetEventObject() is self._txt_desc
        col = COL_DESC if is_desc else COL_NOTES
        new_value = self._txt_desc.GetValue() if is_desc else self._txt_notes.GetValue()

        # Update model and DVC for the edited row
        if is_desc:
            self._rows[row_idx].description = new_value
        else:
            self._rows[row_idx].notes = new_value
        self._dvc.SetTextValue(new_value, row_idx, col)

        # Bulk-sync to all other checked rows if this row is also checked
        if self._is_checked(row_idx):
            for i in range(self._dvc.GetItemCount()):
                if i != row_idx and self._is_checked(i):
                    if is_desc:
                        self._rows[i].description = new_value
                    else:
                        self._rows[i].notes = new_value
                    self._dvc.SetTextValue(new_value, i, col)

    def _on_select_all(self, event) -> None:
        for i in range(self._dvc.GetItemCount()):
            self._dvc.SetToggleValue(True, i, COL_CHECK)

    def _on_select_none(self, event) -> None:
        for i in range(self._dvc.GetItemCount()):
            self._dvc.SetToggleValue(False, i, COL_CHECK)

    def _on_apply(self, event) -> None:
        def log(msg):
            pass

        try:
            n = commit_edits(self.board, self._rows, log=log)
            if n:
                wx.MessageBox(
                    f"Updated {n} component(s).",
                    "Done",
                    wx.OK | wx.ICON_INFORMATION,
                )
            self.EndModal(wx.ID_OK)
        except Exception:
            import traceback

            wx.MessageBox(traceback.format_exc(), "Error", wx.OK | wx.ICON_ERROR)
