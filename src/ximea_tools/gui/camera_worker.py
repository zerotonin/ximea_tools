# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — gui.camera_worker                                 ║
# ║  « camera grab loop in its own QThread »                         ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Owns a XimeaCamera (or FakeCamera), runs the grab loop via      ║
# ║  chained QTimer.singleShot calls so the Qt event loop stays      ║
# ║  live for slot delivery, and routes frames to the preview        ║
# ║  and (when armed) to an Mp4Writer + sidecar CSV.                 ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Camera grab loop that runs in its own QThread."""

from __future__ import annotations

import csv
import logging
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TextIO

from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from ..camera import XimeaCamera
from ..config import CameraConfig, RecordingConfig
from ..constants import FILENAME_TIMESTAMP_FORMAT
from ..writer import Mp4Writer
from .fake_camera import FakeCamera

log = logging.getLogger(__name__)


class CameraWorker(QObject):
    """QObject that runs the camera grab loop on a dedicated thread.

    All public mutators are slots so they can be invoked across threads
    via Qt's queued connection.  The grab loop is driven by chained
    ``QTimer.singleShot`` calls so the event loop stays responsive.
    """

    frameReady    = pyqtSignal(object, object)   # (np.ndarray, FrameMeta)
    statusChanged = pyqtSignal(int, int, float)  # written, dropped, elapsed
    error         = pyqtSignal(str)
    started       = pyqtSignal()
    stopped       = pyqtSignal()
    recordingStateChanged = pyqtSignal(bool, str)  # (is_recording, video_path)

    def __init__(self, config: CameraConfig, use_fake: bool = False) -> None:
        super().__init__()
        self._config = config
        self._use_fake = use_fake
        self._camera: XimeaCamera | FakeCamera | None = None
        self._running = False
        self._recording = False
        self._writer: Mp4Writer | None = None
        self._csv_file: TextIO | None = None
        self._csv_writer: object = None  # csv._writer.writer; not statically typed
        self._record_t0 = 0.0
        self._record_frame_idx = 0
        self._max_record_frames: int | None = None
        self._video_path: Path | None = None

    # ─── lifecycle ───────────────────────────────────────────────
    @pyqtSlot()
    def start(self) -> None:
        try:
            self._open_camera()
        except Exception as e:
            log.exception("Camera open failed")
            self.error.emit(f"Camera open failed: {e}")
            return
        self._running = True
        self.started.emit()
        QTimer.singleShot(0, self._grab_one)

    @pyqtSlot()
    def stop(self) -> None:
        self._running = False  # grab loop will tear down on next tick

    # ─── live setters (no restart needed) ────────────────────────
    @pyqtSlot(int)
    def set_exposure(self, us: int) -> None:
        if self._camera is None:
            return
        try:
            self._camera.set_exposure(us)
            self._config = replace(self._config, exposure_us=us)
        except Exception as e:
            log.warning("set_exposure failed: %s", e)

    @pyqtSlot(float)
    def set_framerate(self, fps: float) -> None:
        if self._camera is None:
            return
        try:
            self._camera.set_framerate(fps)
            self._config = replace(self._config, fps=fps)
        except Exception as e:
            log.warning("set_framerate failed: %s", e)

    @pyqtSlot(float)
    def set_gain(self, db: float) -> None:
        if self._camera is None:
            return
        try:
            self._camera.set_gain(db)
            self._config = replace(self._config, gain_db=db)
        except Exception as e:
            log.warning("set_gain failed: %s", e)

    @pyqtSlot(object)
    def reconfigure(self, new_config: CameraConfig) -> None:
        """Stop, replace config, restart — required for ROI and trigger changes."""
        was_running = self._running
        if was_running:
            self._teardown_camera()
            self._running = False
        self._config = new_config
        if was_running:
            try:
                self._open_camera()
            except Exception as e:
                self.error.emit(f"Reconfigure failed: {e}")
                return
            self._running = True
            QTimer.singleShot(0, self._grab_one)

    # ─── recording ───────────────────────────────────────────────
    @pyqtSlot(object)
    def start_recording(self, rec_cfg: RecordingConfig) -> None:
        if self._recording or self._camera is None:
            return
        try:
            rec_cfg.output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self._abort_recording_start(f"Cannot create {rec_cfg.output_dir}: {e}")
            return

        ts = datetime.now().strftime(FILENAME_TIMESTAMP_FORMAT)
        stem = f"{rec_cfg.filename_prefix}{ts}" if rec_cfg.filename_prefix else ts
        video_path = rec_cfg.output_dir / f"{stem}.mp4"
        meta_path  = rec_cfg.output_dir / f"{stem}.frames.csv"

        writer: Mp4Writer | None = None
        csv_file: TextIO | None = None
        try:
            writer = Mp4Writer(
                video_path, self._config.fps, self._camera.frame_shape,
                queue_size=rec_cfg.queue_size,
            )
            writer.__enter__()
            csv_file = meta_path.open("w", newline="")
        except Exception as e:
            if writer is not None:
                try:
                    writer.__exit__(None, None, None)
                except Exception as ce:
                    log.debug("Writer cleanup after failed start: %s", ce)
            if csv_file is not None:
                try:
                    csv_file.close()
                except Exception as ce:
                    log.debug("CSV cleanup after failed start: %s", ce)
            self._abort_recording_start(f"Failed to open recording target: {e}")
            return

        self._writer = writer
        self._csv_file = csv_file
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow(["frame_idx", "ts_host_s", "ts_cam_s", "acq_nframe"])
        self._record_t0 = time.time()
        self._record_frame_idx = 0
        self._max_record_frames = (
            int(rec_cfg.duration_s * self._config.fps)
            if rec_cfg.duration_s else None
        )
        self._video_path = video_path
        self._recording = True
        log.info("Recording start -> %s", video_path)
        self.recordingStateChanged.emit(True, str(video_path))

    def _abort_recording_start(self, message: str) -> None:
        """Emit the error and reset the recording toggle without crashing the slot."""
        log.error("start_recording aborted: %s", message)
        self.error.emit(message)
        self.recordingStateChanged.emit(False, "")

    @pyqtSlot()
    def stop_recording(self) -> None:
        if not self._recording:
            return
        self._recording = False
        if self._writer is not None:
            self._writer.__exit__(None, None, None)
            self._writer = None
        if self._csv_file is not None:
            self._csv_file.close()
            self._csv_file = None
            self._csv_writer = None
        log.info("Recording stopped after %d frames", self._record_frame_idx)
        self.recordingStateChanged.emit(False, str(self._video_path or ""))

    # ─── internals ───────────────────────────────────────────────
    def _open_camera(self) -> None:
        klass = FakeCamera if self._use_fake else XimeaCamera
        cam = klass(self._config)
        cam.__enter__()
        cam.start()
        self._camera = cam

    def _teardown_camera(self) -> None:
        if self._camera is None:
            return
        try:
            self._camera.stop()
        except Exception as e:
            log.debug("stop during teardown: %s", e)
        try:
            self._camera.__exit__(None, None, None)
        except Exception as e:
            log.debug("__exit__ during teardown: %s", e)
        self._camera = None

    @pyqtSlot()
    def _grab_one(self) -> None:
        if not self._running:
            if self._recording:
                self.stop_recording()
            self._teardown_camera()
            self.stopped.emit()
            return
        try:
            frame, meta = self._camera.grab()
        except Exception as e:
            log.exception("Grab failed")
            self.error.emit(f"Grab failed: {e}")
            self._running = False
            return
        if self._recording and self._writer is not None:
            self._writer.submit(frame)
            self._csv_writer.writerow(
                [self._record_frame_idx, meta.ts_host_s, meta.ts_cam_s, meta.acq_nframe]
            )
            self._record_frame_idx += 1
            elapsed = time.time() - self._record_t0
            self.statusChanged.emit(
                self._writer.frames_written,
                self._writer.frames_dropped,
                elapsed,
            )
            if (self._max_record_frames is not None
                    and self._record_frame_idx >= self._max_record_frames):
                self.stop_recording()
        self.frameReady.emit(frame, meta)
        QTimer.singleShot(0, self._grab_one)
