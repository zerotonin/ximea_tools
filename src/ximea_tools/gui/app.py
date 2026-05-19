# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — gui.app                                           ║
# ║  « argparse + QApplication entry point (ximea-gui) »             ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Parses --device / --fake / --uvc / --serial, instantiates the   ║
# ║  MainWindow, optionally shows a camera picker when several are   ║
# ║  available, wires SIGINT cleanup, and runs the Qt event loop.    ║
# ╚══════════════════════════════════════════════════════════════════╝
"""``ximea-gui`` console script entry point."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from dataclasses import replace

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from ..discovery import CameraInfo, list_all_cameras
from .camera_picker import CameraPickerDialog
from .main_window import MainWindow
from .settings import Settings, load_settings, save_settings


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ximea-gui", description="ximea_tools GUI.")
    p.add_argument("--device", type=str, default=None, metavar="BACKEND:ID",
                   help="Camera spec, e.g. 'ximea:ABC123' or 'uvc:/dev/video0'.")
    p.add_argument("--pick", action="store_true",
                   help="Always show the camera picker, even when one device is found.")
    p.add_argument("--fake", action="store_true",
                   help="Shortcut for --device=fake:.")
    p.add_argument("--uvc", type=int, nargs="?", const=0, default=None, metavar="N",
                   help="Shortcut for --device=uvc:/dev/videoN (default 0).")
    p.add_argument("--serial", type=str, default=None,
                   help="Shortcut for --device=ximea:SERIAL.")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Enable INFO-level logging.")
    return p


def _spec_from_args(args: argparse.Namespace) -> tuple[str, str] | None:
    """Translate the various legacy flags into a single (backend, id) tuple."""
    if args.device:
        backend, _, identifier = args.device.partition(":")
        return (backend, identifier)
    if args.fake:
        return ("fake", "")
    if args.uvc is not None:
        return ("uvc", f"/dev/video{args.uvc}")
    if args.serial:
        return ("ximea", args.serial)
    return None


def _resolve_camera(
    explicit: tuple[str, str] | None,
    settings: Settings,
    force_pick: bool,
) -> tuple[str, str] | None:
    """Pick which camera to open.  Returns ``(backend, identifier)`` or None on cancel."""
    if explicit is not None and explicit[0] == "fake":
        return ("fake", "")

    cameras = list_all_cameras()

    if explicit is not None and explicit[0] != "fake":
        return explicit  # user told us; honour even if the device is not visible

    if not cameras:
        # nothing to pick from — let the worker try and fail with a nice error
        return ("ximea", settings.last_device or "")

    if not force_pick and len(cameras) == 1:
        c = cameras[0]
        return (c.backend, c.identifier)

    # remembered device still present?
    if not force_pick:
        for c in cameras:
            if c.backend == settings.last_backend and c.identifier == settings.last_device:
                return (c.backend, c.identifier)

    dlg = CameraPickerDialog(cameras, preselect=settings.last_device or None)
    if dlg.exec_() != dlg.Accepted:
        return None
    chosen = dlg.selected_camera()
    if chosen is None:
        return None
    return (chosen.backend, chosen.identifier)


def _backend_args_for_worker(backend: str, identifier: str) -> tuple[str, int]:
    """Convert (backend, identifier) into the (backend, device_index) the worker wants."""
    if backend == "uvc":
        # /dev/videoN  → N
        try:
            return ("uvc", int(identifier.removeprefix("/dev/video")))
        except ValueError:
            return ("uvc", 0)
    return (backend if backend in ("ximea", "fake") else "ximea", 0)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    )

    qt_argv = sys.argv if argv is None else [sys.argv[0], *argv]
    app = QApplication(qt_argv)

    settings = load_settings()
    chosen = _resolve_camera(_spec_from_args(args), settings, force_pick=args.pick)
    if chosen is None:
        print("Camera selection cancelled.", file=sys.stderr)
        return 1
    backend_id, identifier = chosen

    # Remember selection for next launch.
    settings = replace(settings, last_backend=backend_id, last_device=identifier)
    save_settings(settings)

    # XIMEA serial sneaks into CameraConfig (legacy path).
    if backend_id == "ximea" and identifier:
        settings = replace(settings,
                           camera=replace(settings.camera, serial=identifier))

    backend, device_index = _backend_args_for_worker(backend_id, identifier)
    window = MainWindow(settings, backend=backend, device_index=device_index)
    window.show()

    signal.signal(signal.SIGINT, lambda *_a: app.quit())
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
