# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — gui.main_window                                   ║
# ║  « top-level QMainWindow assembling the docks »                  ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Central widget = PreviewWidget; right docks = controls,         ║
# ║  recording, trigger; bottom dock = histogram; status bar =       ║
# ║  fps / dropped / written / queue.  Loads and persists            ║
# ║  settings via gui.settings.                                      ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Top-level QMainWindow assembling docks, worker, and menu."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

from PyQt5.QtCore import QThread, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (
    QAction,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
)

from ..config import CameraConfig
from ..constants import SETTINGS_PATH
from .camera_worker import CameraWorker
from .controls_dock import CameraControlsDock
from .histogram_widget import HistogramWidget
from .preview_widget import PreviewWidget
from .recording_dock import RecordingControlsDock
from .settings import Settings, load_settings, save_settings
from .trigger_dock import TriggerDock


class MainWindow(QMainWindow):
    """Main GUI window for ximea_tools."""

    # signals out to worker
    _setExposureRequested      = pyqtSignal(int)
    _setFramerateRequested     = pyqtSignal(float)
    _setGainRequested          = pyqtSignal(float)
    _reconfigureRequested      = pyqtSignal(object)
    _recordingStartRequested   = pyqtSignal(object)
    _recordingStopRequested    = pyqtSignal()
    _stopWorkerRequested       = pyqtSignal()

    def __init__(self, settings: Settings, use_fake: bool = False) -> None:
        super().__init__()
        self.setWindowTitle("ximea_tools" + ("  [FAKE]" if use_fake else ""))
        self._settings  = settings
        self._use_fake  = use_fake

        # widgets and docks
        self.preview    = PreviewWidget()
        self.histogram  = HistogramWidget(update_hz=settings.histogram_hz)
        self.controls   = CameraControlsDock()
        self.recording  = RecordingControlsDock()
        self.trigger    = TriggerDock()
        self.histDock   = QDockWidget("Histogram", self)
        self.histDock.setWidget(self.histogram)

        self.setCentralWidget(self.preview)
        self.addDockWidget(Qt.RightDockWidgetArea,  self.controls)
        self.addDockWidget(Qt.RightDockWidgetArea,  self.recording)
        self.addDockWidget(Qt.RightDockWidgetArea,  self.trigger)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.histDock)

        # status bar widgets
        self.fpsLabel    = QLabel("0.0 fps")
        self.writtenLbl  = QLabel("written: 0")
        self.droppedLbl  = QLabel("dropped: 0")
        self.cuesLabel   = QLabel("cues: —")
        for w in (self.fpsLabel, self.writtenLbl, self.droppedLbl, self.cuesLabel):
            self.statusBar().addPermanentWidget(w)
        self.statusBar().showMessage("idle")

        self._build_menu()
        self._apply_settings(settings)
        self._wire_signals()
        self._start_worker()

        self._fps_alpha = 0.1
        self._fps_value = 0.0
        self._last_frame_t: float | None = None

    # ─── setup ────────────────────────────────────────────────────
    def _apply_settings(self, s: Settings) -> None:
        self.controls.load_from_config(s.camera)
        self.recording.load_from_config(s.recording)
        self.trigger.load_from_config(s.camera.trigger_mode, s.camera.gpi_port)
        self.resize(*s.window_size)

    def _wire_signals(self) -> None:
        self.controls.exposureChanged.connect(self._setExposureRequested.emit)
        self.controls.fpsChanged.connect(self._setFramerateRequested.emit)
        self.controls.gainChanged.connect(self._setGainRequested.emit)
        self.controls.roiApplyRequested.connect(self._on_roi_apply)
        self.trigger.triggerApplyRequested.connect(self._on_trigger_apply)
        self.preview.roiSelected.connect(self.controls.set_pending_roi)
        self.recording.recordingStartRequested.connect(self._recordingStartRequested.emit)
        self.recording.recordingStopRequested.connect(self._recordingStopRequested.emit)

    def _start_worker(self) -> None:
        self.worker = CameraWorker(self._settings.camera, use_fake=self._use_fake)
        self.thread = QThread(self)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.start)
        self.worker.frameReady.connect(self._on_frame)
        self.worker.statusChanged.connect(self.recording.update_status)
        self.worker.statusChanged.connect(self._on_record_status)
        self.worker.recordingStateChanged.connect(self.recording.on_recording_state_changed)
        self.worker.error.connect(self._on_error)
        self.worker.stopped.connect(self.thread.quit)

        self._setExposureRequested.connect(self.worker.set_exposure)
        self._setFramerateRequested.connect(self.worker.set_framerate)
        self._setGainRequested.connect(self.worker.set_gain)
        self._reconfigureRequested.connect(self.worker.reconfigure)
        self._recordingStartRequested.connect(self.worker.start_recording)
        self._recordingStopRequested.connect(self.worker.stop_recording)
        self._stopWorkerRequested.connect(self.worker.stop)

        self.thread.start()

    def _build_menu(self) -> None:
        m_file = self.menuBar().addMenu("&File")
        m_file.addAction(QAction("Save preset as…", self, triggered=self._save_preset_as))
        m_file.addAction(QAction("Load preset…", self, triggered=self._load_preset))
        m_file.addSeparator()
        m_file.addAction(QAction("&Quit", self, triggered=self.close, shortcut="Ctrl+Q"))

        m_view = self.menuBar().addMenu("&View")
        for dock in (self.controls, self.recording, self.trigger, self.histDock):
            m_view.addAction(dock.toggleViewAction())

        m_help = self.menuBar().addMenu("&Help")
        m_help.addAction(QAction("About", self, triggered=self._about))

    # ─── frame / status slots ────────────────────────────────────
    @pyqtSlot(object, object)
    def _on_frame(self, frame, _meta) -> None:
        self.preview.set_frame(frame)
        self.histogram.set_frame(frame)
        now = time.time()
        if self._last_frame_t is not None:
            dt = now - self._last_frame_t
            if dt > 0:
                inst = 1.0 / dt
                self._fps_value = (1 - self._fps_alpha) * self._fps_value + self._fps_alpha * inst
                self.fpsLabel.setText(f"{self._fps_value:.1f} fps")
        self._last_frame_t = now

    @pyqtSlot(int, int, float)
    def _on_record_status(self, written: int, dropped: int, _elapsed_s: float) -> None:
        self.writtenLbl.setText(f"written: {written}")
        self.droppedLbl.setText(f"dropped: {dropped}")

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        self.statusBar().showMessage(f"Error: {msg}", 8000)
        if "open failed" in msg.lower():
            self.preview.set_no_frame_text(f"no camera\n({msg})")
        else:
            QMessageBox.warning(self, "Camera error", msg)

    # ─── reconfigure ─────────────────────────────────────────────
    @pyqtSlot(object, object)
    def _on_roi_apply(self, size, offset) -> None:
        new_cam = replace(self._settings.camera, roi_size=size, roi_offset=offset)
        self._settings = replace(self._settings, camera=new_cam)
        self._reconfigureRequested.emit(new_cam)

    @pyqtSlot(str, int)
    def _on_trigger_apply(self, mode: str, port: int) -> None:
        new_cam = replace(self._settings.camera, trigger_mode=mode, gpi_port=port)
        self._settings = replace(self._settings, camera=new_cam)
        self._reconfigureRequested.emit(new_cam)

    # ─── menu actions ────────────────────────────────────────────
    def _save_preset_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save preset", "", "TOML (*.toml)")
        if path:
            save_settings(self._current_settings(), Path(path))
            self.statusBar().showMessage(f"Saved preset to {path}", 3000)

    def _load_preset(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load preset", "", "TOML (*.toml)")
        if not path:
            return
        s = load_settings(Path(path))
        self._settings = s
        self._apply_settings(s)
        self._reconfigureRequested.emit(s.camera)

    def _about(self) -> None:
        QMessageBox.about(
            self, "ximea_tools",
            "<b>ximea_tools</b><br/>"
            "Linux toolbox for XIMEA industrial cameras.<br/>"
            "Bart R.H. Geurten · University of Otago",
        )

    # ─── shutdown ────────────────────────────────────────────────
    def _current_settings(self) -> Settings:
        cam_fields  = self.controls.to_config_fields()
        trig_fields = self.trigger.to_fields()
        try:
            cam = CameraConfig(**cam_fields, **trig_fields, serial=self._settings.camera.serial)
        except (ValueError, TypeError):
            cam = self._settings.camera
        return Settings(
            camera=cam,
            recording=self.recording.to_config(),
            window_size=(self.width(), self.height()),
            histogram_hz=self._settings.histogram_hz,
        )

    def closeEvent(self, event: object) -> None:
        try:
            save_settings(self._current_settings(), SETTINGS_PATH)
        except Exception:
            pass
        self._stopWorkerRequested.emit()
        self.thread.wait(3000)
        event.accept()
