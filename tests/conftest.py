"""Stub KiCad-only modules so plugin code can be imported outside KiCad."""

import sys
from unittest.mock import MagicMock

# wx is only available inside KiCad's bundled Python environment.
sys.modules.setdefault("wx", MagicMock())

# Ensure the plugin directory is on sys.path so imports resolve.
import os  # noqa: E402

plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)
