# KiCad Build Document Generator Plugin
# Place this folder in your KiCad scripting/plugins directory

import pcbnew
import wx
import os
import sys

plugin_dir = os.path.dirname(os.path.realpath(__file__))

# Both the plugin dir itself and vendored lib/ must be on the path.
# realpath() resolves symlinks so imports work when the plugin is symlinked.
for _p in [plugin_dir, os.path.join(plugin_dir, "lib")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


class BuildDocPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Build Document Generator"
        self.category = "Documentation"
        self.description = "Generate a PedalPCB-style build document PDF (cover, BOM, schematic)"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(plugin_dir, "icon.png")

    def Run(self):
        board = pcbnew.GetBoard()
        if board is None:
            wx.MessageBox("No board loaded.", "Build Doc Generator", wx.OK | wx.ICON_ERROR)
            return

        # Show the dialog
        from build_doc_dialog import BuildDocDialog
        dlg = BuildDocDialog(None, board)
        dlg.ShowModal()
        dlg.Destroy()


# Register the plugin
BuildDocPlugin().register()
