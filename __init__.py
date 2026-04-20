"""Build Document Generator — IPC plugin package init.

The plugin is launched via ipc_plugin_main.py by KiCad's IPC runtime.
This file exists only to make the directory a Python package so that
intra-package relative imports resolve correctly.
"""

import os
import sys

plugin_dir = os.path.dirname(os.path.realpath(__file__))
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)
