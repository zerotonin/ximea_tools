# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — uvc_camera                                        ║
# ║  « V4L2/UVC fallback for cheap USB webcams »                     ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Same API as XimeaCamera but backed by cv2.VideoCapture so the   ║
# ║  GUI can be exercised on any /dev/videoN device when the         ║
# ║  XIMEA is unavailable.  Frames come out as 3-channel BGR uint8.  ║
# ╚══════════════════════════════════════════════════════════════════╝
"""V4L2/UVC camera wrapper with the XimeaCamera interface."""

from __future__ import annotations

import logging
import time
from typing import Iterator

import cv2
import numpy as np

from .camera import FrameMeta
from .config import CameraConfig

log = logging.getLogger(__name__)


class UvcCamera:
    """USB Video Class camera via OpenCV's V4L2 backend.

    Mirrors :class:`ximea_tools.camera.XimeaCamera` so it can be
    dropped into :class:`ximea_tools.gui.camera_worker.CameraWorker`
    without conditional logic at call sites.

    Webcam controls are quirky and vendor-dependent.  We call
    ``cap.set(...)`` best-effort; if a property is not supported the
    call silently returns False and the GUI slider just has no effect.
    """

    def __init__(self, config: CameraConfig, device_index: int = 0) -> None:
        self._config = config
        self._device_index = device_index
        self._cap: cv2.VideoCapture | None = None
        self.frame_shape: tuple[int, int] | None = None
        self._t0 = 0.0
        self._frame_idx = 0

    # ─── lifecycle ────────────────────────────────────────────────
    def __enter__(self) -> "UvcCamera":
        cap = cv2.VideoCapture(self._device_index, cv2.CAP_V4L2)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open /dev/video{self._device_index}")
        self._cap = cap
        self._apply_config()
        ok, frame = cap.read()
        if not ok:
            cap.release()
            self._cap = None
            raise RuntimeError(
                f"/dev/video{self._device_index} opened but first read failed"
            )
        self.frame_shape = frame.shape[:2]
        self._t0 = time.time()
        log.info("UvcCamera open — %s", self.describe())
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    # ─── configuration (best-effort) ──────────────────────────────
    def _apply_config(self) -> None:
        cap = self._cap
        cfg = self._config
        if cfg.roi_size is not None:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  cfg.roi_size[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.roi_size[1])
        cap.set(cv2.CAP_PROP_FPS, cfg.fps)
        # 1 = manual on V4L2 backend; 3 = aperture-priority (auto).
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
        cap.set(cv2.CAP_PROP_EXPOSURE, cfg.exposure_us / 100.0)
        if cfg.gain_db > 0:
            cap.set(cv2.CAP_PROP_GAIN, cfg.gain_db)

    # ─── live setters ─────────────────────────────────────────────
    def set_exposure(self, us: int) -> None:
        if self._cap is not None:
            self._cap.set(cv2.CAP_PROP_EXPOSURE, us / 100.0)

    def set_framerate(self, fps: float) -> None:
        if self._cap is not None:
            self._cap.set(cv2.CAP_PROP_FPS, fps)

    def set_gain(self, db: float) -> None:
        if self._cap is not None:
            self._cap.set(cv2.CAP_PROP_GAIN, db)

    # ─── acquisition ──────────────────────────────────────────────
    def start(self) -> None: ...   # VideoCapture is continuous
    def stop(self)  -> None: ...

    def grab(self) -> tuple[np.ndarray, FrameMeta]:
        ok, frame = self._cap.read()
        if not ok:
            raise RuntimeError(f"UVC read failed on /dev/video{self._device_index}")
        meta = FrameMeta(
            acq_nframe=self._frame_idx,
            ts_host_s=time.time(),
            ts_cam_s=time.time() - self._t0,
        )
        self._frame_idx += 1
        return frame, meta

    def frames(self) -> Iterator[tuple[np.ndarray, FrameMeta]]:
        self.start()
        try:
            while True:
                yield self.grab()
        finally:
            self.stop()

    # ─── introspection ────────────────────────────────────────────
    def describe(self) -> str:
        c = self._config
        return (
            f"UVC /dev/video{self._device_index} exposure={c.exposure_us}us "
            f"fps={c.fps} gain={c.gain_db}dB shape={self.frame_shape}"
        )
