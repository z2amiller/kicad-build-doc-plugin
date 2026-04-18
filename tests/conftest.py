"""Stub KiCad-only modules so plugin code can be imported outside KiCad."""

import sys
from unittest.mock import MagicMock

# pcbnew and wx are only available inside KiCad's bundled Python environment.
# Stub them out before any plugin module (including __init__.py) is loaded.
pcbnew_mock = MagicMock()
pcbnew_mock.ToMM.side_effect = lambda x: x / 1_000_000  # nanometres → mm
sys.modules.setdefault("pcbnew", pcbnew_mock)
sys.modules.setdefault("wx", MagicMock())

# Ensure the plugin directory is on sys.path so imports resolve.
import os  # noqa: E402

plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Only add the plugin dir itself — lib/ contains compiled extensions built for
# KiCad's bundled Python and won't work with the system interpreter.
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)
