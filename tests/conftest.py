"""Stub KiCad-only modules so plugin code can be imported outside KiCad."""

import sys
from unittest.mock import MagicMock

# wx is only available inside KiCad's bundled Python environment.
sys.modules.setdefault("wx", MagicMock())

# kipy is only available inside KiCad's IPC environment.
_kipy = MagicMock()
sys.modules.setdefault("kipy", _kipy)
sys.modules.setdefault("kipy.board", _kipy.board)
sys.modules.setdefault("kipy.proto", _kipy.proto)
sys.modules.setdefault("kipy.proto.common", _kipy.proto.common)
sys.modules.setdefault("kipy.proto.common.v1", _kipy.proto.common.v1)

# Ensure the plugin directory is on sys.path so imports resolve.
import os  # noqa: E402

plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)
