# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — camera                                            ║
# ║  « context-managed XIMEA camera wrapper »                        ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Thin layer over xiapi.Camera that applies a CameraConfig,       ║
# ║  yields (frame, FrameMeta) pairs, and guarantees the device      ║
# ║  handle is released on exit (even on exception).                 ║
# ║                                                                  ║
# ║  Import of `ximea.xiapi` is deferred to __enter__ so the         ║
# ║  module can be unit-tested without the system SDK present.       ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Context-managed XIMEA camera wrapper."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterator

import numpy as np

from .capabilities import CameraCapabilities  # noqa: F401 — re-exported by typing
from .config import CameraConfig

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
#  xiapi string constants  (see xidefs.py in the XIMEA SDK)
# ─────────────────────────────────────────────────────────────────
_TIMING_FRAMERATE  = "XI_ACQ_TIMING_MODE_FRAME_RATE"
_TRIG_OFF          = "XI_TRG_OFF"
_TRIG_EDGE_RISING  = "XI_TRG_EDGE_RISING"
_TRIG_EDGE_FALLING = "XI_TRG_EDGE_FALLING"
_GPI_TRIGGER       = "XI_GPI_TRIGGER"

_TRIGGER_MAP: dict[str, str] = {
    "free_run":     _TRIG_OFF,
    "edge_rising":  _TRIG_EDGE_RISING,
    "edge_falling": _TRIG_EDGE_FALLING,
}


@dataclass(frozen=True)
class FrameMeta:
    """Per-frame metadata exported by :meth:`XimeaCamera.grab`."""

    acq_nframe: int    # camera's own frame counter — gaps indicate drops
    ts_host_s:  float  # host wall-clock, seconds since epoch
    ts_cam_s:   float  # camera timestamp, tsSec + tsUSec * 1e-6


class XimeaCamera:
    """Context manager around ``xiapi.Camera`` configured by a CameraConfig.

    Example:
        >>> with XimeaCamera(CameraConfig(exposure_us=10_000, fps=30)) as cam:
        ...     for frame, meta in cam.frames():
        ...         process(frame)

    The ``ximea`` module is imported lazily on ``__enter__`` so this class
    can be imported in environments without the SDK (tests, docs, CI).
    """

    def __init__(self, config: CameraConfig) -> None:
        self._config = config
        self._cam = None
        self._img = None
        self._xiapi = None
        self.frame_shape: tuple[int, int] | None = None  # (H, W) after ROI

    # ─── lifecycle ────────────────────────────────────────────────
    def __enter__(self) -> "XimeaCamera":
        from ximea import xiapi  # lazy import: keeps tests/docs ximea-free

        self._xiapi = xiapi
        self._cam = xiapi.Camera()
        if self._config.serial is None:
            self._cam.open_device()
        else:
            self._cam.open_device_by_SN(self._config.serial)
        self._apply_config()
        self._img = xiapi.Image()
        self.frame_shape = self._read_frame_shape()
        log.info("Camera open — %s", self.describe())
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._cam is None:
            return
        try:
            self._cam.stop_acquisition()
        except Exception as e:  # noqa: BLE001 — best-effort cleanup
            log.debug("stop_acquisition during exit: %s", e)
        self._cam.close_device()
        self._cam = None
        log.info("Camera closed")

    # ─── configuration ────────────────────────────────────────────
    def _apply_config(self) -> None:
        cfg = self._config
        cam = self._cam
        cam.set_exposure(cfg.exposure_us)
        cam.set_acq_timing_mode(_TIMING_FRAMERATE)
        cam.set_framerate(cfg.fps)
        if cfg.gain_db > 0:
            cam.set_gain(cfg.gain_db)
        if cfg.roi_size is not None:
            cam.set_width(cfg.roi_size[0])
            cam.set_height(cfg.roi_size[1])
        if cfg.roi_offset != (0, 0):
            cam.set_offsetX(cfg.roi_offset[0])
            cam.set_offsetY(cfg.roi_offset[1])
        self._apply_trigger(cfg)

    def _apply_trigger(self, cfg: CameraConfig) -> None:
        self._cam.set_trigger_source(_TRIGGER_MAP[cfg.trigger_mode])
        if cfg.trigger_mode != "free_run":
            self._cam.set_gpi_selector(f"XI_GPI_PORT{cfg.gpi_port}")
            self._cam.set_gpi_mode(_GPI_TRIGGER)

    def _read_frame_shape(self) -> tuple[int, int]:
        """Return (height, width) as the camera reports them post-ROI."""
        w = int(self._cam.get_width())
        h = int(self._cam.get_height())
        return (h, w)

    # ─── live setters (no restart required) ───────────────────────
    def set_exposure(self, us: int) -> None:
        if self._cam is not None:
            self._cam.set_exposure(us)

    def set_framerate(self, fps: float) -> None:
        if self._cam is not None:
            self._cam.set_framerate(fps)

    def set_gain(self, db: float) -> None:
        if self._cam is not None:
            self._cam.set_gain(db)

    # ─── acquisition ──────────────────────────────────────────────
    def start(self) -> None:
        if self._cam is not None:
            self._cam.start_acquisition()

    def stop(self) -> None:
        if self._cam is not None:
            self._cam.stop_acquisition()

    def grab(self) -> tuple[np.ndarray, FrameMeta]:
        """Block until the next frame is available; return ``(frame, meta)``."""
        self._cam.get_image(self._img)
        frame = self._img.get_image_data_numpy()
        meta = FrameMeta(
            acq_nframe=int(self._img.acq_nframe),
            ts_host_s=time.time(),
            ts_cam_s=float(self._img.tsSec) + float(self._img.tsUSec) * 1e-6,
        )
        return frame, meta

    def frames(self) -> Iterator[tuple[np.ndarray, FrameMeta]]:
        """Yield ``(frame, meta)`` pairs until the caller breaks the loop."""
        self.start()
        try:
            while True:
                yield self.grab()
        finally:
            self.stop()

    def capabilities(self) -> "CameraCapabilities":
        """Query xiapi for sensor size and parameter ranges."""
        from .capabilities import probe_ximea_capabilities  # lazy: avoid cycle
        if self._cam is None:
            from .capabilities import CameraCapabilities
            return CameraCapabilities()
        return probe_ximea_capabilities(self._cam)

    # ─── introspection ────────────────────────────────────────────
    def describe(self) -> str:
        cfg = self._config
        roi = f"{cfg.roi_size}+{cfg.roi_offset}" if cfg.roi_size else "full"
        return (
            f"exposure={cfg.exposure_us}us fps={cfg.fps} gain={cfg.gain_db}dB "
            f"roi={roi} trigger={cfg.trigger_mode} shape={self.frame_shape}"
        )
