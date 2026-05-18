# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — gui.preview_widget                                ║
# ║  « live frame viewer with rubber-band ROI »                      ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  QLabel-backed widget that displays the latest np.ndarray as     ║
# ║  a scaled QImage, draws a translucent ROI rubber-band on         ║
# ║  mouse drag, and emits roiSelected(x,y,w,h) in source-frame      ║
# ║  coordinates on release.                                         ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Live preview widget with rubber-band ROI."""

from __future__ import annotations

import numpy as np
from PyQt5.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QPainter, QPen
from PyQt5.QtWidgets import QWidget

from ..constants import WONG


def numpy_to_qimage(arr: np.ndarray) -> QImage:
    """Convert a mono or BGR uint8 array to a self-owning QImage."""
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    if arr.ndim == 2:
        h, w = arr.shape
        contig = np.ascontiguousarray(arr)
        return QImage(contig.data, w, h, w, QImage.Format_Grayscale8).copy()
    if arr.ndim == 3 and arr.shape[2] == 3:
        rgb = np.ascontiguousarray(arr[..., ::-1])
        h, w = rgb.shape[:2]
        return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
    raise ValueError(f"Unsupported frame shape {arr.shape}")


class PreviewWidget(QWidget):
    """Scaled live preview that emits ROI selections in frame coordinates."""

    roiSelected = pyqtSignal(int, int, int, int)  # x, y, w, h

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        self._qimage: QImage | None = None
        self._drag_start: QPoint | None = None
        self._drag_end:   QPoint | None = None
        self._no_frame_text = "no camera"

    # ─── public API ──────────────────────────────────────────────
    def set_frame(self, arr: np.ndarray) -> None:
        self._qimage = numpy_to_qimage(arr)
        self.update()

    def set_no_frame_text(self, text: str) -> None:
        self._no_frame_text = text
        self.update()

    # ─── painting ────────────────────────────────────────────────
    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("black"))
        if self._qimage is None:
            painter.setPen(QPen(QColor("#CCCCCC")))
            painter.drawText(self.rect(), Qt.AlignCenter, self._no_frame_text)
            return
        target = self._image_rect()
        painter.drawImage(target, self._qimage)
        if self._drag_start is not None and self._drag_end is not None:
            band = QRect(self._drag_start, self._drag_end).normalized()
            painter.setPen(QPen(QColor(WONG["orange"]), 2, Qt.DashLine))
            painter.drawRect(band)

    # ─── mouse → rubber-band ROI ─────────────────────────────────
    def mousePressEvent(self, event: object) -> None:
        if event.button() == Qt.LeftButton and self._qimage is not None:
            self._drag_start = event.pos()
            self._drag_end = event.pos()
            self.update()

    def mouseMoveEvent(self, event: object) -> None:
        if self._drag_start is not None:
            self._drag_end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event: object) -> None:
        if event.button() != Qt.LeftButton or self._drag_start is None:
            return
        self._drag_end = event.pos()
        roi = self._compute_roi()
        self._drag_start = None
        self._drag_end = None
        self.update()
        if roi is not None and roi[2] > 0 and roi[3] > 0:
            self.roiSelected.emit(*roi)

    # ─── geometry helpers ────────────────────────────────────────
    def _image_rect(self) -> QRect:
        ww, wh = self.width(), self.height()
        iw, ih = self._qimage.width(), self._qimage.height()
        scale = min(ww / iw, wh / ih)
        dw, dh = int(iw * scale), int(ih * scale)
        return QRect((ww - dw) // 2, (wh - dh) // 2, dw, dh)

    def _compute_roi(self) -> tuple[int, int, int, int] | None:
        if self._qimage is None or self._drag_start is None or self._drag_end is None:
            return None
        target = self._image_rect()
        iw, ih = self._qimage.width(), self._qimage.height()
        scale = iw / target.width()
        band = QRect(self._drag_start, self._drag_end).normalized()
        x1 = max(0.0, (band.left()   - target.left()) * scale)
        y1 = max(0.0, (band.top()    - target.top())  * scale)
        x2 = min(float(iw), (band.right()  - target.left()) * scale)
        y2 = min(float(ih), (band.bottom() - target.top())  * scale)
        return int(x1), int(y1), int(x2 - x1), int(y2 - y1)
