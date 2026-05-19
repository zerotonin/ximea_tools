# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — gui.recording_dock                                ║
# ║  « output, duration, queue, and start/stop »                     ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Builds a RecordingConfig from form fields and toggles the       ║
# ║  worker's recording state.  Status row shows frames written,     ║
# ║  dropped, and elapsed wall-time.                                 ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Recording control dock with Start/Stop toggle, filename builder, and live status."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from ..config import RecordingConfig
from ..constants import DEFAULT_OUTPUT_DIR
from ..recorder import build_stem


_PATTERN_TEMPLATE = "{prefix_}YYYY-MM-DD__HH-MM-SS{_suffix}.mp4"


class RecordingControlsDock(QDockWidget):
    """Dock controlling where recordings go and when they start/stop."""

    recordingStartRequested = pyqtSignal(object)  # RecordingConfig
    recordingStopRequested  = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Recording", parent)

        widget = QWidget()
        form = QFormLayout(widget)

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

        # ┌─── filename template explainer ──────────────────────────
        self.patternLabel = QLabel(f"Pattern:  <code>{_PATTERN_TEMPLATE}</code>")
        self.patternLabel.setTextFormat(1)  # Qt.RichText
        self.patternLabel.setStyleSheet("color: #888;")
        form.addRow(self.patternLabel)

        self.exampleLabel = QLabel("")
        self.exampleLabel.setStyleSheet("font-family: monospace;")
        form.addRow("Example", self.exampleLabel)
        # └──────────────────────────────────────────────────────────

        self.monochromeCheck = QCheckBox("Save as monochrome MP4 (saves space)")
        form.addRow(self.monochromeCheck)

        self.durationSpin = QDoubleSpinBox()
        self.durationSpin.setRange(0.0, 86_400.0 * 7)
        self.durationSpin.setSuffix(" s")
        self.durationSpin.setDecimals(1)
        self.durationSpin.setSpecialValueText("unlimited")
        self.durationSpin.setValue(0.0)
        form.addRow("Duration", self.durationSpin)

        self.queueSpin = QSpinBox()
        self.queueSpin.setRange(1, 1000)
        self.queueSpin.setValue(30)
        form.addRow("Queue", self.queueSpin)

        self.recordBtn = QPushButton("● Start Recording")
        self.recordBtn.setCheckable(True)
        form.addRow(self.recordBtn)

        self.statusLabel = QLabel("idle")
        form.addRow("Status", self.statusLabel)

        self.setWidget(widget)

        self.dirBtn.clicked.connect(self._browse_output_dir)
        self.recordBtn.toggled.connect(self._on_record_toggled)
        self.prefixEdit.textChanged.connect(self._refresh_example)
        self.suffixEdit.textChanged.connect(self._refresh_example)
        self._refresh_example()

    # ─── public slots ────────────────────────────────────────────
    @pyqtSlot(int, int, float)
    def update_status(self, written: int, dropped: int, elapsed_s: float) -> None:
        self.statusLabel.setText(
            f"{written} frames · {dropped} dropped · {elapsed_s:.1f} s"
        )

    @pyqtSlot(bool, str)
    def on_recording_state_changed(self, is_recording: bool, video_path: str) -> None:
        """Sync UI when worker confirms/finishes recording."""
        if not is_recording:
            self.recordBtn.blockSignals(True)
            self.recordBtn.setChecked(False)
            self.recordBtn.setText("● Start Recording")
            self.recordBtn.blockSignals(False)
            self.statusLabel.setText(f"saved: {Path(video_path).name}" if video_path else "idle")
            self._refresh_example()

    def load_from_config(self, cfg: RecordingConfig) -> None:
        self.dirEdit.setText(str(cfg.output_dir))
        self.prefixEdit.setText(cfg.filename_prefix)
        self.suffixEdit.setText(cfg.filename_suffix)
        self.durationSpin.setValue(cfg.duration_s if cfg.duration_s else 0.0)
        self.queueSpin.setValue(cfg.queue_size)
        self.monochromeCheck.setChecked(cfg.monochrome)
        self._refresh_example()

    def to_config(self) -> RecordingConfig:
        return RecordingConfig(
            output_dir=Path(self.dirEdit.text()),
            duration_s=self.durationSpin.value() if self.durationSpin.value() > 0 else None,
            filename_prefix=self.prefixEdit.text(),
            filename_suffix=self.suffixEdit.text(),
            queue_size=self.queueSpin.value(),
            monochrome=self.monochromeCheck.isChecked(),
        )

    # ─── private ─────────────────────────────────────────────────
    def _browse_output_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Output directory", self.dirEdit.text())
        if d:
            self.dirEdit.setText(d)

    def _on_record_toggled(self, on: bool) -> None:
        if on:
            self.recordBtn.setText("■ Stop Recording")
            self.recordingStartRequested.emit(self.to_config())
        else:
            self.recordBtn.setText("● Start Recording")
            self.recordingStopRequested.emit()

    def _refresh_example(self) -> None:
        stem = build_stem(self.prefixEdit.text(), self.suffixEdit.text(),
                          ts=datetime.now())
        self.exampleLabel.setText(f"{stem}.mp4")
