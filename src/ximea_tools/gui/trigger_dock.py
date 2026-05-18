# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — gui.trigger_dock                                  ║
# ║  « external-trigger mode (XIMEA GPI side) »                      ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Selects free_run, edge_rising, or edge_falling on a GPI         ║
# ║  port.  The host-side CueWire event source lands in Sprint       ║
# ║  4 and will plug in next to this dock.                           ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Trigger-mode dock — selects XIMEA GPI behaviour."""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QWidget,
)


class TriggerDock(QDockWidget):
    """Dock controlling the XIMEA-side external trigger mode."""

    triggerApplyRequested = pyqtSignal(str, int)  # (mode, gpi_port)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Trigger", parent)

        widget = QWidget()
        form = QFormLayout(widget)

        self.modeCombo = QComboBox()
        self.modeCombo.addItems(["free_run", "edge_rising", "edge_falling"])
        form.addRow("Mode", self.modeCombo)

        self.gpiSpin = QSpinBox()
        self.gpiSpin.setRange(1, 2)
        self.gpiSpin.setValue(1)
        form.addRow("GPI port", self.gpiSpin)

        self.applyBtn = QPushButton("Apply (restarts camera)")
        form.addRow(self.applyBtn)

        note = QLabel(
            "<i>CueWire host-side event source<br/>arrives in Sprint 4.</i>"
        )
        note.setStyleSheet("color: #888;")
        form.addRow(note)

        self.setWidget(widget)

        self.applyBtn.clicked.connect(self._on_apply)

    def load_from_config(self, mode: str, gpi_port: int) -> None:
        idx = self.modeCombo.findText(mode)
        if idx >= 0:
            self.modeCombo.setCurrentIndex(idx)
        self.gpiSpin.setValue(gpi_port)

    def to_fields(self) -> dict:
        return {
            "trigger_mode": self.modeCombo.currentText(),
            "gpi_port":     self.gpiSpin.value(),
        }

    def _on_apply(self) -> None:
        self.triggerApplyRequested.emit(self.modeCombo.currentText(), self.gpiSpin.value())
