# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — gui.recording_dock                                ║
# ║  « mode-aware recording controls »                               ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Top combo selects the recording mode; a QStackedWidget swaps    ║
# ║  mode-specific parameter widgets below; the shared bottom row    ║
# ║  carries the main toggle (and a Trigger button in ring mode).    ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Recording control dock — mode selector, parameters, start/stop."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import RecordingConfig
from ..constants import DEFAULT_OUTPUT_DIR
from ..recorder import build_stem


_PATTERN_TEMPLATE = "{prefix_}YYYY-MM-DD__HH-MM-SS{_suffix}.mp4"

_MODE_LABELS = [
    ("Free run",                  "free_run"),
    ("Timed duration",            "timed"),
    ("Ring buffer (pre + post)",  "ring_buffer"),
    ("External trigger (v0.6)",   "external"),
]


class RecordingControlsDock(QDockWidget):
    """Mode-aware recording dock."""

    recordingStartRequested = pyqtSignal(object)  # RecordingConfig
    recordingStopRequested  = pyqtSignal()
    armRingBufferRequested  = pyqtSignal(object)  # RecordingConfig
    triggerRingSaveRequested = pyqtSignal()
    disarmRingBufferRequested = pyqtSignal()
    monochromePreviewToggled = pyqtSignal(bool)
    memoryPredictionChanged  = pyqtSignal()      # internal repaint cue

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Recording", parent)

        root = QWidget()
        outer = QVBoxLayout(root)

        # ─── mode selector ───────────────────────────────────────
        self.modeCombo = QComboBox()
        for label, key in _MODE_LABELS:
            self.modeCombo.addItem(label, key)
        outer.addWidget(QLabel("Mode"))
        outer.addWidget(self.modeCombo)
        outer.addWidget(self._hline())

        # ─── shared form (output, filenames, monochrome, queue) ──
        shared = QWidget()
        form = QFormLayout(shared)

        dir_row = QHBoxLayout()
        self.dirEdit = QLineEdit(str(DEFAULT_OUTPUT_DIR))
        self.dirBtn  = QPushButton("Browse…")
        dir_row.addWidget(self.dirEdit)
        dir_row.addWidget(self.dirBtn)
        form.addRow("Output dir", dir_row)

        self.prefixEdit = QLineEdit("")
        self.prefixEdit.setPlaceholderText("optional, before timestamp")
        form.addRow("Prefix", self.prefixEdit)

        self.suffixEdit = QLineEdit("")
        self.suffixEdit.setPlaceholderText("optional, after timestamp")
        form.addRow("Suffix", self.suffixEdit)

        self.patternLabel = QLabel(f"Pattern:  <code>{_PATTERN_TEMPLATE}</code>")
        self.patternLabel.setTextFormat(1)  # Qt.RichText
        self.patternLabel.setStyleSheet("color: #888;")
        form.addRow(self.patternLabel)

        self.exampleLabel = QLabel("")
        self.exampleLabel.setStyleSheet("font-family: monospace;")
        form.addRow("Example", self.exampleLabel)

        self.monochromeCheck = QCheckBox("Save as monochrome MP4 (saves space)")
        form.addRow(self.monochromeCheck)

        self.queueSpin = QSpinBox()
        self.queueSpin.setRange(1, 1000)
        self.queueSpin.setValue(30)
        form.addRow("Queue", self.queueSpin)

        outer.addWidget(shared)
        outer.addWidget(self._hline())

        # ─── mode-specific parameters (QStackedWidget) ───────────
        self.modeStack = QStackedWidget()

        # Page 0: free_run (no extra params)
        self.modeStack.addWidget(QLabel(
            "<i>Start records until you press Stop.</i>"
        ))

        # Page 1: timed (duration)
        page_timed = QWidget()
        tlayout = QFormLayout(page_timed)
        self.durationSpin = QDoubleSpinBox()
        self.durationSpin.setRange(0.1, 86_400.0 * 7)
        self.durationSpin.setSuffix(" s")
        self.durationSpin.setDecimals(1)
        self.durationSpin.setValue(10.0)
        tlayout.addRow("Duration", self.durationSpin)
        self.modeStack.addWidget(page_timed)

        # Page 2: ring buffer (pre / post / RAM + memory predictor + bars)
        page_ring = QWidget()
        rlayout = QFormLayout(page_ring)
        self.preSpin = QDoubleSpinBox()
        self.preSpin.setRange(0.0, 300.0)
        self.preSpin.setSuffix(" s")
        self.preSpin.setDecimals(1)
        self.preSpin.setValue(5.0)
        rlayout.addRow("Pre-trigger", self.preSpin)
        self.postSpin = QDoubleSpinBox()
        self.postSpin.setRange(0.0, 300.0)
        self.postSpin.setSuffix(" s")
        self.postSpin.setDecimals(1)
        self.postSpin.setValue(2.0)
        rlayout.addRow("Post-trigger", self.postSpin)
        self.ramSpin = QSpinBox()
        self.ramSpin.setRange(16, 65_536)
        self.ramSpin.setSuffix(" MB")
        self.ramSpin.setValue(1024)
        rlayout.addRow("RAM cap", self.ramSpin)

        self.memoryLabel = QLabel("memory: —")
        self.memoryLabel.setStyleSheet("font-family: monospace; color: #555;")
        rlayout.addRow(self.memoryLabel)

        self.preBar  = QProgressBar()
        self.preBar.setFormat("pre  %v/%m frames")
        self.preBar.setMaximum(1)
        rlayout.addRow(self.preBar)

        self.postBar = QProgressBar()
        self.postBar.setFormat("post %v/%m frames")
        self.postBar.setMaximum(1)
        rlayout.addRow(self.postBar)

        rlayout.addRow(QLabel(
            "<i>Arm fills a rolling buffer; Trigger captures the post-tail,<br/>"
            "then writes pre + post to disk.</i>"
        ))
        self.modeStack.addWidget(page_ring)

        # Page 3: external (placeholder)
        page_ext = QWidget()
        ext_layout = QVBoxLayout(page_ext)
        ext_layout.addWidget(QLabel(
            "<i>External trigger (CueWire) lands in v0.6.<br/>"
            "Once available, arming here will start the recording when<br/>"
            "the host receives a cue event.</i>"
        ))
        self.modeStack.addWidget(page_ext)

        outer.addWidget(self.modeStack)
        outer.addWidget(self._hline())

        # ─── action buttons ──────────────────────────────────────
        self.recordBtn = QPushButton("● Start Recording")
        self.recordBtn.setCheckable(True)
        outer.addWidget(self.recordBtn)

        self.triggerBtn = QPushButton("📷 Trigger & Save")
        self.triggerBtn.setEnabled(False)
        self.triggerBtn.hide()
        outer.addWidget(self.triggerBtn)

        self.statusLabel = QLabel("idle")
        outer.addWidget(self.statusLabel)

        outer.addStretch(1)
        self.setWidget(root)

        # ─── connections ─────────────────────────────────────────
        self.dirBtn.clicked.connect(self._browse_output_dir)
        self.recordBtn.toggled.connect(self._on_record_toggled)
        self.triggerBtn.clicked.connect(self._on_trigger_pressed)
        self.prefixEdit.textChanged.connect(self._refresh_example)
        self.suffixEdit.textChanged.connect(self._refresh_example)
        self.modeCombo.currentIndexChanged.connect(self._on_mode_changed)
        self.monochromeCheck.toggled.connect(self.monochromePreviewToggled.emit)
        self.monochromeCheck.toggled.connect(self._refresh_memory_label)
        for spin in (self.preSpin, self.postSpin, self.ramSpin):
            spin.valueChanged.connect(self._refresh_memory_label)

        # Frame shape comes from the worker once the camera is open.
        self._frame_shape: tuple[int, int] = (480, 640)
        self._fps: float = 30.0

        self._refresh_example()
        self._on_mode_changed(self.modeCombo.currentIndex())
        self._refresh_memory_label()

    # ─── public slots ────────────────────────────────────────────
    @pyqtSlot(int, int, float)
    def update_status(self, written: int, dropped: int, elapsed_s: float) -> None:
        self.statusLabel.setText(
            f"{written} frames · {dropped} dropped · {elapsed_s:.1f} s"
        )

    @pyqtSlot(bool, str)
    def on_recording_state_changed(self, is_active: bool, video_path: str) -> None:
        """Worker signals when a free/timed recording starts/ends or a ring saves."""
        if not is_active:
            self.recordBtn.blockSignals(True)
            self.recordBtn.setChecked(False)
            self.recordBtn.blockSignals(False)
            self._refresh_buttons_for_mode()
            self.triggerBtn.setEnabled(False)
            if video_path:
                self.statusLabel.setText(f"saved: {Path(video_path).name}")
            else:
                self.statusLabel.setText("idle")
            self._refresh_example()
        else:
            # active — leave button in 'on' state; update text if available
            mode = self.modeCombo.currentData()
            if mode == "ring_buffer" and video_path == "armed":
                self.statusLabel.setText("armed — fill buffer, then trigger")
                self.triggerBtn.setEnabled(True)
            elif video_path and video_path not in ("armed",):
                self.statusLabel.setText(video_path)

    @pyqtSlot(str, int, int)
    def on_ring_buffer_state_changed(self, state: str, fill: int, total: int) -> None:
        if state == "armed":
            pct = (fill * 100 // total) if total else 0
            self.statusLabel.setText(f"armed · buffer {fill}/{total} ({pct}%)")
            self.triggerBtn.setEnabled(True)
            self.preBar.setMaximum(max(1, total))
            self.preBar.setValue(min(fill, total))
            self.postBar.setMaximum(max(1, int(self.postSpin.value() * self._fps)))
            self.postBar.setValue(0)
        elif state == "post":
            self.statusLabel.setText("capturing post-trigger frames…")
            self.triggerBtn.setEnabled(False)
            # `fill` here is the latest pre-fill — keep it; `total` is pre_frames.
            self.preBar.setValue(self.preBar.maximum())
            cap = self.postBar.maximum()
            self.postBar.setValue(min(self.postBar.value() + 1, cap))
        elif state == "writing":
            self.statusLabel.setText("writing buffer to disk…")
            self.triggerBtn.setEnabled(False)
            self.postBar.setValue(self.postBar.maximum())
        elif state == "idle":
            self.triggerBtn.setEnabled(False)
            self.preBar.setValue(0)
            self.postBar.setValue(0)

    @pyqtSlot(tuple, float)
    def update_frame_context(self, frame_shape: tuple, fps: float) -> None:
        """Called by the main window once the camera is open / on reconfigure."""
        self._frame_shape = tuple(frame_shape)
        self._fps = float(fps)
        self._refresh_memory_label()

    def load_from_config(self, cfg: RecordingConfig) -> None:
        self.dirEdit.setText(str(cfg.output_dir))
        self.prefixEdit.setText(cfg.filename_prefix)
        self.suffixEdit.setText(cfg.filename_suffix)
        self.queueSpin.setValue(cfg.queue_size)
        self.monochromeCheck.setChecked(cfg.monochrome)
        if cfg.duration_s is not None:
            self.durationSpin.setValue(cfg.duration_s)
        self.preSpin.setValue(cfg.ring_pre_seconds)
        self.postSpin.setValue(cfg.ring_post_seconds)
        self.ramSpin.setValue(cfg.ring_max_ram_mb)
        idx = self.modeCombo.findData(cfg.mode)
        if idx >= 0:
            self.modeCombo.setCurrentIndex(idx)
        self._refresh_example()

    def to_config(self) -> RecordingConfig:
        mode = self.modeCombo.currentData() or "free_run"
        duration = self.durationSpin.value() if mode == "timed" else None
        return RecordingConfig(
            output_dir=Path(self.dirEdit.text()),
            duration_s=duration,
            filename_prefix=self.prefixEdit.text(),
            filename_suffix=self.suffixEdit.text(),
            queue_size=self.queueSpin.value(),
            monochrome=self.monochromeCheck.isChecked(),
            mode=mode,
            ring_pre_seconds=self.preSpin.value(),
            ring_post_seconds=self.postSpin.value(),
            ring_max_ram_mb=self.ramSpin.value(),
        )

    # ─── private ─────────────────────────────────────────────────
    @staticmethod
    def _hline() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    def _browse_output_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Output directory", self.dirEdit.text())
        if d:
            self.dirEdit.setText(d)

    def _on_mode_changed(self, idx: int) -> None:
        self.modeStack.setCurrentIndex(idx)
        self._refresh_buttons_for_mode()

    def _refresh_buttons_for_mode(self) -> None:
        mode = self.modeCombo.currentData()
        is_ring = (mode == "ring_buffer")
        is_external = (mode == "external")
        self.triggerBtn.setVisible(is_ring)
        self.recordBtn.setEnabled(not is_external)
        checked = self.recordBtn.isChecked()
        if mode == "free_run":
            self.recordBtn.setText("■ Stop Recording" if checked else "● Start Recording")
        elif mode == "timed":
            self.recordBtn.setText("■ Stop Recording" if checked else "● Start (timed)")
        elif mode == "ring_buffer":
            self.recordBtn.setText("■ Disarm" if checked else "▶ Arm Ring Buffer")
        else:  # external
            self.recordBtn.setText("(connect CueWire)")

    def _on_record_toggled(self, on: bool) -> None:
        mode = self.modeCombo.currentData()
        cfg = self.to_config()
        if mode == "ring_buffer":
            if on:
                self.armRingBufferRequested.emit(cfg)
            else:
                self.disarmRingBufferRequested.emit()
        else:
            if on:
                self.recordingStartRequested.emit(cfg)
            else:
                self.recordingStopRequested.emit()
        self._refresh_buttons_for_mode()

    def _on_trigger_pressed(self) -> None:
        self.triggerBtn.setEnabled(False)
        self.triggerRingSaveRequested.emit()

    def _refresh_example(self) -> None:
        stem = build_stem(self.prefixEdit.text(), self.suffixEdit.text(),
                          ts=datetime.now())
        self.exampleLabel.setText(f"{stem}.mp4")

    def _refresh_memory_label(self, *_args) -> None:
        h, w = self._frame_shape
        bpp = 1 if self.monochromeCheck.isChecked() else 3
        bytes_per_frame = h * w * bpp
        pre_frames  = int(self.preSpin.value()  * self._fps)
        post_frames = int(self.postSpin.value() * self._fps)
        ram_cap_mb  = self.ramSpin.value()
        cap_frames  = max(1, int((ram_cap_mb * 1_000_000) / max(1, bytes_per_frame)))
        effective_pre  = min(pre_frames,  cap_frames)
        effective_post = min(post_frames, cap_frames)
        predicted_mb = (effective_pre + effective_post) * bytes_per_frame / 1_000_000
        clamped = " (clamped by RAM cap)" if pre_frames > effective_pre else ""
        avail = _available_ram_mb()
        avail_str = f"{avail} MB available" if avail >= 0 else "available unknown"
        self.memoryLabel.setText(
            f"memory: predicted ≈ {predicted_mb:.0f} MB / "
            f"{avail_str}{clamped}"
        )
        # Update bar maxima so the user sees the budget even before arming.
        self.preBar.setMaximum(max(1, effective_pre))
        self.postBar.setMaximum(max(1, effective_post))


def _available_ram_mb() -> int:
    """Return MemAvailable in MB from /proc/meminfo, or -1 if unavailable."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return -1
