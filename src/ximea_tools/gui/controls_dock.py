# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — gui.controls_dock                                 ║
# ║  « exposure, fps, gain, mode, and ROI controls »                 ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Slider+spinbox combos that emit live deltas for exposure,       ║
# ║  framerate, and gain.  Mode combo (for UVC) selects the          ║
# ║  native capture resolution.  ROI is set via rubber-band on       ║
# ║  the preview and committed with Apply (camera restarts).         ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Camera control dock: exposure, fps, gain, video mode, ROI."""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QWidget,
)

from ..capabilities import CameraCapabilities, VideoMode
from ..config import CameraConfig
from ..constants import DEFAULT_EXPOSURE_US, DEFAULT_FPS, DEFAULT_GAIN_DB


class CameraControlsDock(QDockWidget):
    """Dock with exposure/fps/gain spinners, mode combo, and deferred ROI."""

    exposureChanged   = pyqtSignal(int)
    fpsChanged        = pyqtSignal(float)
    gainChanged       = pyqtSignal(float)
    roiApplyRequested = pyqtSignal(object, object)            # (size, offset)
    videoModeApplyRequested = pyqtSignal(object)              # (w, h) | None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Camera", parent)

        widget = QWidget()
        form = QFormLayout(widget)

        self.modeCombo = QComboBox()
        self.modeCombo.addItem("native (probe pending)", None)
        form.addRow("Mode", self.modeCombo)

        self.applyModeBtn = QPushButton("Apply mode (restarts camera)")
        form.addRow(self.applyModeBtn)

        self.expSpin = QSpinBox()
        self.expSpin.setRange(1, 1_000_000)
        self.expSpin.setSuffix(" μs")
        self.expSpin.setSingleStep(100)
        self.expSpin.setValue(DEFAULT_EXPOSURE_US)
        form.addRow("Exposure", self.expSpin)

        self.fpsSpin = QDoubleSpinBox()
        self.fpsSpin.setRange(0.1, 500.0)
        self.fpsSpin.setSuffix(" fps")
        self.fpsSpin.setDecimals(2)
        self.fpsSpin.setSingleStep(1.0)
        self.fpsSpin.setValue(DEFAULT_FPS)
        form.addRow("Framerate", self.fpsSpin)

        self.gainSpin = QDoubleSpinBox()
        self.gainSpin.setRange(0.0, 24.0)
        self.gainSpin.setSuffix(" dB")
        self.gainSpin.setSingleStep(0.5)
        self.gainSpin.setDecimals(1)
        self.gainSpin.setValue(DEFAULT_GAIN_DB)
        form.addRow("Gain", self.gainSpin)

        self.roiLabel = QLabel("full sensor")
        form.addRow("ROI", self.roiLabel)

        btns = QHBoxLayout()
        self.applyRoiBtn = QPushButton("Apply ROI")
        self.resetRoiBtn = QPushButton("Reset")
        btns.addWidget(self.applyRoiBtn)
        btns.addWidget(self.resetRoiBtn)
        form.addRow(btns)

        self.setWidget(widget)

        self._pending_size:   tuple[int, int] | None = None
        self._pending_offset: tuple[int, int]        = (0, 0)
        self._capabilities: CameraCapabilities | None = None

        self.expSpin.valueChanged.connect(self.exposureChanged.emit)
        self.fpsSpin.valueChanged.connect(self.fpsChanged.emit)
        self.gainSpin.valueChanged.connect(self.gainChanged.emit)
        self.applyRoiBtn.clicked.connect(self._on_apply_roi)
        self.resetRoiBtn.clicked.connect(self._on_reset_roi)
        self.applyModeBtn.clicked.connect(self._on_apply_mode)

    # ─── slots ────────────────────────────────────────────────────
    @pyqtSlot(int, int, int, int)
    def set_pending_roi(self, x: int, y: int, w: int, h: int) -> None:
        self._pending_size = (w, h)
        self._pending_offset = (x, y)
        self.roiLabel.setText(f"{w}×{h} +{x}+{y}  (pending — click Apply)")

    @pyqtSlot(object)
    def apply_capabilities(self, caps: CameraCapabilities) -> None:
        """Bound spinboxes to real device ranges; populate mode combo."""
        self._capabilities = caps

        if caps.exposure_us is not None:
            self._set_spin_range(self.expSpin,
                                 int(caps.exposure_us.minimum),
                                 int(caps.exposure_us.maximum))
        if caps.gain_db is not None:
            self._set_spin_range(self.gainSpin,
                                 float(caps.gain_db.minimum),
                                 float(caps.gain_db.maximum))
        if caps.fps is not None:
            self._set_spin_range(self.fpsSpin,
                                 float(caps.fps.minimum),
                                 float(caps.fps.maximum))

        self.modeCombo.blockSignals(True)
        self.modeCombo.clear()
        if not caps.modes:
            self.modeCombo.addItem("native", None)
        else:
            # Show each (W, H, pixfmt @ best-fps) entry but the value we store
            # is just (W, H) — pixel format is implementation detail.
            seen: set[tuple[int, int]] = set()
            for m in caps.modes:
                key = (m.width, m.height)
                if key in seen:
                    continue
                seen.add(key)
                best_fps = max(m.fps_options) if m.fps_options else None
                label = f"{m.width}×{m.height}" + (
                    f"  @ {best_fps:g} fps" if best_fps else ""
                )
                self.modeCombo.addItem(label, key)
        self.modeCombo.blockSignals(False)

        self.applyModeBtn.setEnabled(self.modeCombo.count() > 1)

    def load_from_config(self, cfg: CameraConfig) -> None:
        for spin, val in (
            (self.expSpin,  cfg.exposure_us),
            (self.fpsSpin,  cfg.fps),
            (self.gainSpin, cfg.gain_db),
        ):
            spin.blockSignals(True)
            spin.setValue(val)
            spin.blockSignals(False)
        if cfg.roi_size is not None:
            w, h = cfg.roi_size
            x, y = cfg.roi_offset
            self._pending_size = cfg.roi_size
            self._pending_offset = cfg.roi_offset
            self.roiLabel.setText(f"{w}×{h} +{x}+{y}")
        else:
            self._pending_size = None
            self._pending_offset = (0, 0)
            self.roiLabel.setText("full sensor")
        if cfg.video_mode is not None:
            idx = self.modeCombo.findData(cfg.video_mode)
            if idx >= 0:
                self.modeCombo.setCurrentIndex(idx)

    def to_config_fields(self) -> dict:
        """Return current control values as a kwargs dict for CameraConfig."""
        return {
            "exposure_us": self.expSpin.value(),
            "fps":         self.fpsSpin.value(),
            "gain_db":     self.gainSpin.value(),
            "roi_size":    self._pending_size,
            "roi_offset":  self._pending_offset,
            "video_mode":  self.modeCombo.currentData(),
        }

    # ─── private ──────────────────────────────────────────────────
    def _on_apply_roi(self) -> None:
        self.roiApplyRequested.emit(self._pending_size, self._pending_offset)
        if self._pending_size is not None:
            w, h = self._pending_size
            x, y = self._pending_offset
            self.roiLabel.setText(f"{w}×{h} +{x}+{y}")

    def _on_reset_roi(self) -> None:
        self._pending_size = None
        self._pending_offset = (0, 0)
        self.roiLabel.setText("full sensor")
        self.roiApplyRequested.emit(None, (0, 0))

    def _on_apply_mode(self) -> None:
        self.videoModeApplyRequested.emit(self.modeCombo.currentData())

    @staticmethod
    def _set_spin_range(spin, lo, hi) -> None:
        current = spin.value()
        spin.blockSignals(True)
        spin.setRange(lo, hi)
        spin.setValue(max(lo, min(hi, current)))
        spin.blockSignals(False)
