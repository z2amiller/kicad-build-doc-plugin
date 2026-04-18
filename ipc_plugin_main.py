"""IPC plugin entry point for KiCad 9+.

Reads KICAD_API_SOCKET and KICAD_API_TOKEN from environment variables,
connects to the running KiCad instance via kipy, then opens the build
document dialog.
"""
from __future__ import annotations

import logging
import os
import sys
import time

logger = logging.getLogger(__name__)

_WX_APP = None


def _ensure_wx_app():
    global _WX_APP
    try:
        import wx
    except Exception:
        logger.exception("Cannot import wx")
        return None, False
    app = wx.GetApp()
    if app is not None:
        return app, False
    _WX_APP = wx.App(None)
    return _WX_APP, True


def _wait_for_kicad(kicad, timeout_s: float = 8.0) -> bool:
    from kipy.errors import ApiError, ConnectionError as KiPyConnectionError

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            kicad.ping()
            return True
        except (ApiError, KiPyConnectionError, OSError):
            time.sleep(0.2)
    try:
        kicad.ping()
        return True
    except Exception:
        return False


def main() -> int:
    logging.basicConfig(level=logging.INFO)

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)

    socket_path = os.getenv("KICAD_API_SOCKET") or os.getenv("KICAD_IPC_SOCKET")
    token = os.getenv("KICAD_API_TOKEN")

    if not socket_path:
        logger.error("KICAD_API_SOCKET not set — this plugin requires KiCad 9+ with IPC support.")
        return 1

    try:
        from kipy import KiCad
        kicad = KiCad(socket_path=socket_path, kicad_token=token)

        if not _wait_for_kicad(kicad):
            logger.error("Cannot connect to KiCad IPC at %s", socket_path)
            return 1

        board = kicad.get_board()
        logger.info("Connected: board=%s", board.name)
    except Exception:
        logger.exception("Failed to connect to KiCad IPC")
        return 1

    app, created_app = _ensure_wx_app()
    if app is None:
        return 1

    try:
        from build_doc_dialog import BuildDocDialog
        dlg = BuildDocDialog(None, board)
        dlg.ShowModal()
        dlg.Destroy()
    except Exception:
        logger.exception("Dialog error")
        return 1

    if created_app:
        app.MainLoop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
