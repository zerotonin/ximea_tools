# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — gui.recording_dock                                ║
# ║  « output, duration, queue, and start/stop »                     ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Builds a RecordingConfig from form fields and toggles the       ║
# ║  worker's recording state.  Status row shows frames written,     ║
# ║  dropped, and elapsed wall-time.                                 ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Recording control dock with Start/Stop toggle and live status."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (
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

    def load_from_config(self, cfg: RecordingConfig) -> None:
        self.dirEdit.setText(str(cfg.output_dir))
        self.prefixEdit.setText(cfg.filename_prefix)
        self.durationSpin.setValue(cfg.duration_s if cfg.duration_s else 0.0)
        self.queueSpin.setValue(cfg.queue_size)

    def to_config(self) -> RecordingConfig:
        return RecordingConfig(
            output_dir=Path(self.dirEdit.text()),
            duration_s=self.durationSpin.value() if self.durationSpin.value() > 0 else None,
            filename_prefix=self.prefixEdit.text(),
            queue_size=self.queueSpin.value(),
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
