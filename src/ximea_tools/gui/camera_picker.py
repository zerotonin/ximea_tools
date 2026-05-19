# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — gui.camera_picker                                 ║
# ║  « modal dialog for choosing a camera »                          ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Shown on launch when more than one camera is detected, or       ║
# ║  when the user invokes File > Switch camera.  Returns the        ║
# ║  selected CameraInfo or None on cancel.                          ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Camera picker dialog."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..discovery import CameraInfo, list_all_cameras


class CameraPickerDialog(QDialog):
    """Modal dialog: pick one of the detected cameras (or cancel)."""

    def __init__(
        self,
        cameras: list[CameraInfo] | None = None,
        preselect: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select a camera")
        self.setMinimumWidth(480)

        self._cameras = cameras if cameras is not None else list_all_cameras()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"{len(self._cameras)} camera"
            f"{'s' if len(self._cameras) != 1 else ''} detected:"
        ))

        self.list = QListWidget()
        for cam in self._cameras:
            item = QListWidgetItem(
                f"{cam.name}   —   {cam.backend}: {cam.identifier}"
            )
            item.setData(Qt.UserRole, cam)
            self.list.addItem(item)
            if preselect and cam.identifier == preselect:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and self._cameras:
            self.list.setCurrentRow(0)
        layout.addWidget(self.list)

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())

    def selected_camera(self) -> CameraInfo | None:
        item = self.list.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)
