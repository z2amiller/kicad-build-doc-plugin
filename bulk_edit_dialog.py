"""Bulk Description/Notes editor dialog for footprints on the board."""
from __future__ import annotations

import wx
import wx.dataview as dv

from footprint_editor import FootprintRow, commit_edits, load_footprints

# Column indices
COL_CHECK = 0
COL_REF = 1
COL_VALUE = 2
COL_TYPE = 3
COL_DESC = 4
COL_NOTES = 5


class BulkEditDialog(wx.Dialog):
    def __init__(self, parent, board):
        super().__init__(
            parent,
            title="Edit Component Descriptions",
            size=(900, 560),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.board = board
        self._rows: list[FootprintRow] = load_footprints(board)
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
                "Check rows to enable bulk sync — editing any checked cell "
                "updates all other checked rows in the same column."
            ),
        )
        info.Wrap(860)
        vbox.Add(info, flag=wx.ALL, border=10)

        # DataViewListCtrl
        self._dvc = dv.DataViewListCtrl(
            panel,
            style=dv.DV_ROW_LINES | dv.DV_VERT_RULES,
        )
        self._dvc.AppendToggleColumn("", width=30)
        self._dvc.AppendTextColumn("Ref",         width=60,  mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("Value",       width=100, mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("Type",        width=130, mode=dv.DATAVIEW_CELL_INERT)
        self._dvc.AppendTextColumn("Description", width=220, mode=dv.DATAVIEW_CELL_EDITABLE)
        self._dvc.AppendTextColumn("Notes",       width=220, mode=dv.DATAVIEW_CELL_EDITABLE)

        self._dvc.Bind(dv.EVT_DATAVIEW_ITEM_VALUE_CHANGED, self._on_cell_changed)
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
            self._dvc.AppendItem([False, row.ref, row.value, row.fp_type,
                                   row.description, row.notes])

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _is_checked(self, item_row: int) -> bool:
        return bool(self._dvc.GetToggleValue(item_row, COL_CHECK))

    def _sync_row_to_model(self, item_row: int) -> None:
        self._rows[item_row].description = self._dvc.GetTextValue(item_row, COL_DESC)
        self._rows[item_row].notes = self._dvc.GetTextValue(item_row, COL_NOTES)

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_cell_changed(self, event: dv.DataViewEvent) -> None:
        item = event.GetItem()
        col = event.GetColumn()
        item_row = self._dvc.ItemToRow(item)
        if item_row < 0:
            return

        # Sync the edited row to the model
        self._sync_row_to_model(item_row)

        # Bulk-sync editable columns only if the changed row is checked
        if col in (COL_DESC, COL_NOTES) and self._is_checked(item_row):
            new_value = self._dvc.GetTextValue(item_row, col)
            for i in range(self._dvc.GetItemCount()):
                if i != item_row and self._is_checked(i):
                    self._dvc.SetTextValue(new_value, i, col)
                    self._sync_row_to_model(i)

    def _on_select_all(self, event) -> None:
        for i in range(self._dvc.GetItemCount()):
            self._dvc.SetToggleValue(True, i, COL_CHECK)

    def _on_select_none(self, event) -> None:
        for i in range(self._dvc.GetItemCount()):
            self._dvc.SetToggleValue(False, i, COL_CHECK)

    def _on_apply(self, event) -> None:
        # Sync all rows from the DVC to the model before committing
        for i in range(self._dvc.GetItemCount()):
            self._sync_row_to_model(i)

        def log(msg):
            pass  # could wire to a status bar later

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
