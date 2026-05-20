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
from datetime import datetime  # noqa: F401 — kept for downstream import compat
from pathlib import Path
from typing import TextIO

from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from ..camera import XimeaCamera
from ..capabilities import CameraCapabilities
from ..config import CameraConfig, RecordingConfig
from ..recorder import RingBuffer, build_stem
from ..uvc_camera import UvcCamera
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
    capabilitiesReady = pyqtSignal(object)         # CameraCapabilities
    ringBufferStateChanged = pyqtSignal(str, int, int)  # (state, fill, total)
    measuredFpsChanged = pyqtSignal(float)         # smoothed actual fps

    def __init__(
        self,
        config: CameraConfig,
        backend: str = "ximea",
        device_index: int = 0,
    ) -> None:
        super().__init__()
        if backend not in ("ximea", "fake", "uvc"):
            raise ValueError(f"backend must be ximea|fake|uvc, got {backend!r}")
        self._config = config
        self._backend = backend
        self._device_index = device_index
        self._camera: XimeaCamera | FakeCamera | UvcCamera | None = None
        self._running = False
        self._recording = False
        self._writer: Mp4Writer | None = None
        self._csv_file: TextIO | None = None
        self._csv_writer: object = None  # csv._writer.writer; not statically typed
        self._record_t0 = 0.0
        self._record_frame_idx = 0
        self._max_record_seconds: float | None = None
        self._video_path: Path | None = None
        # Ring-buffer state
        self._ring: RingBuffer | None = None
        self._ring_cfg: RecordingConfig | None = None
        self._ring_last_emit = 0
        # Measured fps (EMA of inter-frame delta)
        self._measured_fps = 0.0
        self._fps_samples = 0
        self._last_grab_t: float | None = None
        self._FPS_ALPHA = 0.1
        self._FPS_RELIABLE_AFTER = 20  # samples

    # ─── lifecycle ───────────────────────────────────────────────
    @pyqtSlot()
    def start(self) -> None:
        try:
            self._open_camera()
        except Exception as e:
            log.exception("Camera open failed")
            self.error.emit(f"Camera open failed: {e}")
            return
        try:
            caps = self._camera.capabilities()
            self.capabilitiesReady.emit(caps)
        except Exception as e:
            log.debug("capabilities probe failed: %s", e)
        self._running = True
        self.started.emit()
        QTimer.singleShot(0, self._grab_one)

    @pyqtSlot()
    def stop(self) -> None:
        self._running = False  # grab loop will tear down on next tick

    @pyqtSlot()
    def reset_fps_measurement(self) -> None:
        """Start the EMA fresh — used by the GUI's FPS test button."""
        self._measured_fps = 0.0
        self._fps_samples = 0
        self._last_grab_t = None

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

    @pyqtSlot(bool)
    def set_auto_exposure(self, on: bool) -> None:
        if self._camera is None:
            return
        try:
            self._camera.set_auto_exposure(on)
            self._config = replace(self._config, auto_exposure=on)
        except Exception as e:
            log.warning("set_auto_exposure failed: %s", e)

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

        stem = build_stem(rec_cfg.filename_prefix, rec_cfg.filename_suffix)
        video_path = rec_cfg.output_dir / f"{stem}.mp4"
        meta_path  = rec_cfg.output_dir / f"{stem}.frames.csv"

        writer_fps = self._effective_fps()
        if abs(writer_fps - self._config.fps) > self._config.fps * 0.2:
            log.warning(
                "Measured fps %.2f deviates from configured %.2f — "
                "writing MP4 at measured rate",
                writer_fps, self._config.fps,
            )
        writer: Mp4Writer | None = None
        csv_file: TextIO | None = None
        try:
            writer = Mp4Writer(
                video_path, writer_fps, self._camera.frame_shape,
                queue_size=rec_cfg.queue_size,
                monochrome=rec_cfg.monochrome,
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
        self._max_record_seconds = rec_cfg.duration_s  # None for free-run
        self._video_path = video_path
        self._recording = True
        log.info("Recording start -> %s", video_path)
        self.recordingStateChanged.emit(True, str(video_path))

    def _abort_recording_start(self, message: str) -> None:
        """Emit the error and reset the recording toggle without crashing the slot."""
        log.error("start_recording aborted: %s", message)
        self.error.emit(message)
        self.recordingStateChanged.emit(False, "")

    # ─── ring buffer ─────────────────────────────────────────────
    @pyqtSlot(object)
    def arm_ring_buffer(self, rec_cfg: RecordingConfig) -> None:
        if self._ring is not None or self._camera is None:
            return
        shape = self._camera.frame_shape or (480, 640)
        # XIMEA mono → 1 byte/pix; UVC/Fake BGR → 3 bytes/pix.
        bpp = 1 if self._backend == "ximea" else 3
        try:
            self._ring = RingBuffer(
                pre_seconds=rec_cfg.ring_pre_seconds,
                post_seconds=rec_cfg.ring_post_seconds,
                fps=self._effective_fps(),
                frame_shape=shape,
                bytes_per_pix=bpp,
                max_ram_mb=rec_cfg.ring_max_ram_mb,
            )
        except Exception as e:
            self.error.emit(f"Cannot arm ring buffer: {e}")
            self.recordingStateChanged.emit(False, "")
            return
        self._ring_cfg = rec_cfg
        self._ring_last_emit = 0
        if self._ring.pre_frames_clamped:
            log.warning(
                "Ring buffer pre-frames clamped to %d (RAM cap %d MB)",
                self._ring.pre_frames, rec_cfg.ring_max_ram_mb,
            )
        log.info(
            "Ring buffer armed: pre=%d post=%d frames",
            self._ring.pre_frames, self._ring.post_frames,
        )
        self.recordingStateChanged.emit(True, "armed")
        self.ringBufferStateChanged.emit("armed", 0, self._ring.pre_frames)

    @pyqtSlot()
    def trigger_ring_save(self) -> None:
        if self._ring is None or self._ring.state != "armed":
            return
        self._ring.trigger()
        self.ringBufferStateChanged.emit(
            self._ring.state, self._ring.fill_frames, self._ring.pre_frames,
        )

    @pyqtSlot()
    def disarm_ring_buffer(self) -> None:
        if self._ring is None:
            return
        self._ring = None
        self._ring_cfg = None
        log.info("Ring buffer disarmed; %d frames dropped", 0)
        self.ringBufferStateChanged.emit("idle", 0, 0)
        self.recordingStateChanged.emit(False, "")

    def _flush_ring_to_disk(self) -> None:
        """Called when the ring buffer is in state==done."""
        assert self._ring is not None and self._ring_cfg is not None
        rcfg = self._ring_cfg
        try:
            rcfg.output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.error.emit(f"Cannot create {rcfg.output_dir}: {e}")
            self._ring = None
            self._ring_cfg = None
            self.recordingStateChanged.emit(False, "")
            self.ringBufferStateChanged.emit("idle", 0, 0)
            return

        stem = build_stem(rcfg.filename_prefix, rcfg.filename_suffix)
        video_path = rcfg.output_dir / f"{stem}.mp4"
        meta_path  = rcfg.output_dir / f"{stem}.frames.csv"
        shape = self._camera.frame_shape or (480, 640)

        log.info("Ring buffer flushing %d frames -> %s",
                 self._ring.total_frames, video_path)
        self.ringBufferStateChanged.emit(
            "writing", self._ring.fill_frames, self._ring.total_frames,
        )
        try:
            with Mp4Writer(
                video_path, self._effective_fps(), shape,
                queue_size=rcfg.queue_size, monochrome=rcfg.monochrome,
            ) as writer, meta_path.open("w", newline="") as meta_f:
                csv_writer = csv.writer(meta_f)
                csv_writer.writerow(
                    ["frame_idx", "ts_host_s", "ts_cam_s", "acq_nframe"]
                )
                for idx, (frame, meta) in enumerate(self._ring.frames()):
                    writer.submit(frame)
                    csv_writer.writerow(
                        [idx, meta.ts_host_s, meta.ts_cam_s, meta.acq_nframe]
                    )
        except Exception as e:
            log.exception("Ring buffer flush failed")
            self.error.emit(f"Ring flush failed: {e}")
        finally:
            self._ring = None
            self._ring_cfg = None
        self.recordingStateChanged.emit(False, str(video_path))
        self.ringBufferStateChanged.emit("idle", 0, 0)

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
        if self._backend == "fake":
            cam: XimeaCamera | FakeCamera | UvcCamera = FakeCamera(self._config)
        elif self._backend == "uvc":
            cam = UvcCamera(self._config, device_index=self._device_index)
        else:
            cam = XimeaCamera(self._config)
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

    # ─── effective fps ───────────────────────────────────────────
    @property
    def measured_fps(self) -> float:
        return self._measured_fps

    def _effective_fps(self) -> float:
        """Best estimate of fps for writers and frame budgets."""
        if (self._fps_samples >= self._FPS_RELIABLE_AFTER
                and self._measured_fps > 0.5):
            return self._measured_fps
        return self._config.fps

    def _update_measured_fps(self, ts_host_s: float) -> None:
        if self._last_grab_t is not None:
            dt = ts_host_s - self._last_grab_t
            if dt > 0:
                inst = 1.0 / dt
                if self._measured_fps <= 0:
                    self._measured_fps = inst
                else:
                    self._measured_fps = (
                        (1 - self._FPS_ALPHA) * self._measured_fps
                        + self._FPS_ALPHA * inst
                    )
                self._fps_samples += 1
                # Emit at most a few times per second.
                if self._fps_samples % 10 == 0:
                    self.measuredFpsChanged.emit(self._measured_fps)
        self._last_grab_t = ts_host_s

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
        self._update_measured_fps(meta.ts_host_s)
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
            if (self._max_record_seconds is not None
                    and elapsed >= self._max_record_seconds):
                self.stop_recording()
        if self._ring is not None:
            state = self._ring.push(frame, meta)
            # throttle the buffer-fill signal to once every ~10 frames so
            # the GUI doesn't drown in updates
            self._ring_last_emit += 1
            if self._ring_last_emit >= 10 or state in ("post", "done"):
                self._ring_last_emit = 0
                self.ringBufferStateChanged.emit(
                    state, self._ring.fill_frames, self._ring.pre_frames,
                )
            if state == "done":
                self._flush_ring_to_disk()
        self.frameReady.emit(frame, meta)
        QTimer.singleShot(0, self._grab_one)
