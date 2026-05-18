# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — gui.app                                           ║
# ║  « argparse + QApplication entry point (ximea-gui) »             ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Parses --fake and --serial, instantiates the MainWindow,        ║
# ║  wires SIGINT cleanup, and runs the Qt event loop.               ║
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

from .main_window import MainWindow
from .settings import load_settings


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ximea-gui", description="ximea_tools GUI.")
    p.add_argument("--fake", action="store_true",
                   help="Use the synthetic FakeCamera (no hardware needed).")
    p.add_argument("--serial", type=str, default=None,
                   help="Camera serial number; default = first connected.")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Enable INFO-level logging.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    )

    qt_argv = sys.argv if argv is None else [sys.argv[0], *argv]
    app = QApplication(qt_argv)

    settings = load_settings()
    if args.serial:
        settings = replace(settings, camera=replace(settings.camera, serial=args.serial))

    window = MainWindow(settings, use_fake=args.fake)
    window.show()

    # let SIGINT propagate through the Qt event loop
    signal.signal(signal.SIGINT, lambda *_a: app.quit())
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
