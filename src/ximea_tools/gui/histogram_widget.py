# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — gui.histogram_widget                              ║
# ║  « matplotlib histogram with saturation flag »                   ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Decimated (5 Hz) FigureCanvasQTAgg showing the 8-bit luma       ║
# ║  histogram of the latest frame and turning red when the          ║
# ║  fraction of pixels at 255 exceeds a configurable threshold.     ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Decimated matplotlib histogram with saturation warning."""

from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from ..constants import WONG


class HistogramWidget(QWidget):
    """Periodic histogram of the most recent frame, with saturation flag."""

    def __init__(
        self,
        update_hz: float = 5.0,
        saturation_threshold: float = 0.01,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sat_thresh = saturation_threshold
        self._last_frame: np.ndarray | None = None

        self._figure = Figure(figsize=(4, 2), tight_layout=True)
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._ax = self._figure.add_subplot(111)
        self._ax.set_xlim(0, 255)
        self._ax.set_xlabel("intensity")
        self._ax.set_ylabel("count")
        self._ax.tick_params(labelsize=8)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self._canvas)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._redraw)
        self._timer.start(int(1000.0 / max(update_hz, 0.5)))

    def set_frame(self, arr: np.ndarray) -> None:
        self._last_frame = arr

    def _redraw(self) -> None:
        if self._last_frame is None:
            return
        arr = self._last_frame
        if arr.ndim == 3:
            arr = arr.mean(axis=2).astype(np.uint8)
        hist, _ = np.histogram(arr, bins=256, range=(0, 256))
        sat = float((arr == 255).mean())
        is_hot = sat > self._sat_thresh
        colour = WONG["vermilion"] if is_hot else WONG["blue"]

        self._ax.clear()
        x = np.arange(256)
        self._ax.fill_between(x, hist, color=colour, alpha=0.85, linewidth=0)
        self._ax.set_xlim(0, 255)
        self._ax.set_ylim(bottom=0)
        self._ax.set_xlabel("intensity")
        self._ax.set_title(
            f"saturation: {sat * 100:.2f}%"
            + ("  ⚠ clip" if is_hot else ""),
            fontsize=9, color=colour,
        )
        self._ax.tick_params(labelsize=8)
        self._canvas.draw_idle()
