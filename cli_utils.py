"""Helpers for locating and invoking kicad-cli."""

from __future__ import annotations

import os
import shutil
from typing import Optional

_kicad_cli_override: Optional[str] = None


def set_kicad_cli_path(path: Optional[str]) -> None:
    """Store the kicad-cli path reported by the KiCad IPC API."""
    global _kicad_cli_override
    _kicad_cli_override = path


def find_kicad_cli() -> Optional[str]:
    """Return the path to kicad-cli, or None if not found.

    Preference order:
    1. Path provided by the KiCad IPC API (kicad.kicad_cli_path)
    2. PATH lookup via shutil.which
    3. Hard-coded candidate paths
    """
    if _kicad_cli_override and os.path.exists(_kicad_cli_override):
        return _kicad_cli_override
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
