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

from PyQt5.QtCore import QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (
    QCheckBox,
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

    exposureChanged     = pyqtSignal(int)
    fpsChanged          = pyqtSignal(float)
    gainChanged         = pyqtSignal(float)
    autoExposureChanged = pyqtSignal(bool)
    roiApplyRequested   = pyqtSignal(object, object)          # (size, offset)
    videoModeApplyRequested = pyqtSignal(object)              # (w, h) | None
    switchCameraRequested = pyqtSignal()
    fpsTestRequested      = pyqtSignal()

    _DEBOUNCE_MS = 150  # rate-limit ioctl flood while scrolling

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Camera", parent)

        widget = QWidget()
        form = QFormLayout(widget)

        # ─── Camera switcher row ──────────────────────────────────
        switcher_row = QHBoxLayout()
        self.cameraLabel = QLabel("camera: —")
        self.cameraLabel.setStyleSheet("font-family: monospace;")
        self.switchCameraBtn = QPushButton("🔄 Switch…")
        switcher_row.addWidget(self.cameraLabel, 1)
        switcher_row.addWidget(self.switchCameraBtn)
        form.addRow(switcher_row)

        self.modeCombo = QComboBox()
        self.modeCombo.addItem("native (probe pending)", None)
        form.addRow("Mode", self.modeCombo)

        self.applyModeBtn = QPushButton("Apply mode (restarts camera)")
        form.addRow(self.applyModeBtn)

        self.autoExposureCheck = QCheckBox("Auto exposure")
        self.autoExposureCheck.setChecked(True)
        form.addRow(self.autoExposureCheck)

        lighting_tip = QLabel(
            "<span style='color:#888;'>"
            "💡 More light = shorter auto-exposure = higher fps.<br/>"
            "Disable for a fixed exposure (some UVC cams then drop fps)."
            "</span>"
        )
        lighting_tip.setWordWrap(True)
        form.addRow(lighting_tip)

        self.expSpin = QSpinBox()
        self.expSpin.setRange(1, 1_000_000)
        self.expSpin.setSuffix(" μs")
        self.expSpin.setSingleStep(100)
        self.expSpin.setValue(DEFAULT_EXPOSURE_US)
        self.expSpin.setEnabled(False)  # gated by auto-exposure checkbox
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

        # ─── FPS test ─────────────────────────────────────────────
        self.testFpsBtn = QPushButton("📊 Test framerate (3 s)")
        form.addRow(self.testFpsBtn)
        self.fpsResultLabel = QLabel("")
        self.fpsResultLabel.setStyleSheet("color: #555; font-family: monospace;")
        form.addRow(self.fpsResultLabel)

        self.setWidget(widget)

        self._pending_size:   tuple[int, int] | None = None
        self._pending_offset: tuple[int, int]        = (0, 0)
        self._capabilities: CameraCapabilities | None = None

        # Debounced emission for the live setters — prevents an ioctl
        # flood (and the resulting black/bright flicker) when the user
        # scrolls a spinbox rapidly.
        self._exp_timer  = self._make_debounce(
            lambda: self.exposureChanged.emit(self.expSpin.value())
        )
        self._fps_timer  = self._make_debounce(
            lambda: self.fpsChanged.emit(self.fpsSpin.value())
        )
        self._gain_timer = self._make_debounce(
            lambda: self.gainChanged.emit(self.gainSpin.value())
        )
        self.expSpin.valueChanged.connect(lambda _=0: self._exp_timer.start())
        self.expSpin.editingFinished.connect(self._exp_timer.stop)
        self.expSpin.editingFinished.connect(
            lambda: self.exposureChanged.emit(self.expSpin.value())
        )
        self.fpsSpin.valueChanged.connect(lambda _=0: self._fps_timer.start())
        self.fpsSpin.editingFinished.connect(self._fps_timer.stop)
        self.fpsSpin.editingFinished.connect(
            lambda: self.fpsChanged.emit(self.fpsSpin.value())
        )
        self.gainSpin.valueChanged.connect(lambda _=0: self._gain_timer.start())
        self.gainSpin.editingFinished.connect(self._gain_timer.stop)
        self.gainSpin.editingFinished.connect(
            lambda: self.gainChanged.emit(self.gainSpin.value())
        )

        self.autoExposureCheck.toggled.connect(self.expSpin.setDisabled)
        self.autoExposureCheck.toggled.connect(self.autoExposureChanged.emit)
        self.applyRoiBtn.clicked.connect(self._on_apply_roi)
        self.resetRoiBtn.clicked.connect(self._on_reset_roi)
        self.applyModeBtn.clicked.connect(self._on_apply_mode)
        self.switchCameraBtn.clicked.connect(self.switchCameraRequested.emit)
        self.testFpsBtn.clicked.connect(self._on_test_fps_pressed)

    def set_camera_label(self, backend: str, identifier: str) -> None:
        if backend == "fake":
            self.cameraLabel.setText("camera: FAKE")
        elif identifier:
            self.cameraLabel.setText(f"camera: {backend}:{identifier}")
        else:
            self.cameraLabel.setText(f"camera: {backend}")

    def show_fps_test_result(self, fps: float) -> None:
        self.fpsResultLabel.setText(f"last test: {fps:.1f} fps")
        self.testFpsBtn.setEnabled(True)

    def _on_test_fps_pressed(self) -> None:
        self.testFpsBtn.setEnabled(False)
        self.fpsResultLabel.setText("testing… (3 s)")
        self.fpsTestRequested.emit()

    def _make_debounce(self, slot) -> QTimer:
        t = QTimer(self)
        t.setSingleShot(True)
        t.setInterval(self._DEBOUNCE_MS)
        t.timeout.connect(slot)
        return t

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
        self.autoExposureCheck.blockSignals(True)
        self.autoExposureCheck.setChecked(cfg.auto_exposure)
        self.expSpin.setEnabled(not cfg.auto_exposure)
        self.autoExposureCheck.blockSignals(False)
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
            "exposure_us":   self.expSpin.value(),
            "fps":           self.fpsSpin.value(),
            "gain_db":       self.gainSpin.value(),
            "auto_exposure": self.autoExposureCheck.isChecked(),
            "roi_size":      self._pending_size,
            "roi_offset":    self._pending_offset,
            "video_mode":    self.modeCombo.currentData(),
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
