"""Helpers for locating and invoking kicad-cli."""
from __future__ import annotations

import os
import shutil
from typing import Optional


def find_kicad_cli() -> Optional[str]:
    """Return the path to kicad-cli, or None if not found."""
    found = shutil.which("kicad-cli")
    if found:
        return found
    candidates = [
        "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
        "/usr/local/bin/kicad-cli",
        "/usr/bin/kicad-cli",
    ]
    return next((c for c in candidates if os.path.exists(c)), None)


def kicad_env() -> dict:
    """Return an os.environ copy with KiCad framework paths set (macOS)."""
    env = os.environ.copy()
    env["DYLD_FRAMEWORK_PATH"] = "/Applications/KiCad/KiCad.app/Contents/Frameworks"
    env["DYLD_LIBRARY_PATH"] = "/Applications/KiCad/KiCad.app/Contents/Frameworks"
    return env
