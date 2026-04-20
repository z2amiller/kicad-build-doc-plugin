"""IPC plugin entry point for KiCad 9+.

Reads KICAD_API_SOCKET and KICAD_API_TOKEN from environment variables,
connects to the running KiCad instance via kipy, then opens the build
document dialog.
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
import threading
import time

logger = logging.getLogger(__name__)

_LOCK_FILE = os.path.join(tempfile.gettempdir(), "kicad-builddoc.lock")
_WX_APP = None


def _acquire_instance_lock() -> bool:
    """Return True if this is the only running instance.

    Uses a PID file. Stale locks (dead PID) are silently replaced.
    """
    if os.path.exists(_LOCK_FILE):
        try:
            with open(_LOCK_FILE) as fh:
                pid = int(fh.read().strip())
            os.kill(pid, 0)   # signal 0 = existence check, no signal sent
            return False       # process alive — another instance is running
        except (ValueError, ProcessLookupError):
            pass               # stale lock: bad PID or process gone
        except PermissionError:
            return False       # process alive but owned by another user
    try:
        with open(_LOCK_FILE, "w") as fh:
            fh.write(str(os.getpid()))
    except OSError:
        pass   # can't write lock; don't block the user
    return True


def _release_instance_lock() -> None:
    try:
        os.unlink(_LOCK_FILE)
    except OSError:
        pass


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

    if not _acquire_instance_lock():
        import wx
        wx.MessageBox(
            "Build Document Generator is already running.\n"
            "Close the existing window before opening a new one.",
            "Already Running",
            wx.OK | wx.ICON_INFORMATION,
        )
        return 0

    try:
        from build_doc_dialog import BuildDocDialog
        import wx
        dlg = BuildDocDialog(None, board)

        def _watch_kicad():
            while True:
                time.sleep(3)
                try:
                    kicad.ping()
                except (ConnectionRefusedError, FileNotFoundError, OSError):
                    wx.CallAfter(dlg.EndModal, wx.ID_CANCEL)
                    return
                except Exception:
                    pass  # transient/concurrent error; keep watching

        threading.Thread(target=_watch_kicad, daemon=True).start()
        dlg.ShowModal()
        dlg.Destroy()
    except Exception:
        logger.exception("Dialog error")
        return 1
    finally:
        _release_instance_lock()

    if created_app:
        app.MainLoop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
