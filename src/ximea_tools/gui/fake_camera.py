# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — gui.fake_camera                                   ║
# ║  « synthetic camera for tests and headless dev »                 ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Drop-in replacement for XimeaCamera that emits a moving-        ║
# ║  stripe + noise test pattern.  Used by the GUI when --fake       ║
# ║  is passed and by pytest-qt tests that can't see hardware.       ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Synthetic XIMEA-shaped camera for tests and headless development."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Iterator

import numpy as np

from ..camera import FrameMeta
from ..config import CameraConfig


class FakeCamera:
    """Mimics :class:`ximea_tools.camera.XimeaCamera` without hardware."""

    def __init__(self, config: CameraConfig) -> None:
        self._config = config
        if config.roi_size is not None:
            w, h = config.roi_size
            self.frame_shape: tuple[int, int] = (h, w)
        else:
            self.frame_shape = (480, 640)
        self._frame_idx = 0
        self._t0 = time.time()
        self._rng = np.random.default_rng(seed=0xCAFE)

    # ─── lifecycle ────────────────────────────────────────────────
    def __enter__(self) -> "FakeCamera":
        return self

    def __exit__(self, *_exc: object) -> None:
        pass

    def start(self) -> None: ...
    def stop(self) -> None: ...

    # ─── live setters (match XimeaCamera API) ─────────────────────
    def set_exposure(self, us: int) -> None:
        self._config = replace(self._config, exposure_us=us)

    def set_framerate(self, fps: float) -> None:
        self._config = replace(self._config, fps=fps)

    def set_gain(self, db: float) -> None:
        self._config = replace(self._config, gain_db=db)

    # ─── acquisition ──────────────────────────────────────────────
    def grab(self) -> tuple[np.ndarray, FrameMeta]:
        h, w = self.frame_shape
        frame = self._rng.integers(0, 60, (h, w), dtype=np.uint8)
        stripe_x = (self._frame_idx * 5) % w
        stripe_w = max(8, w // 20)
        frame[:, stripe_x:stripe_x + stripe_w] = 220
        crosshair_y = h // 2
        frame[crosshair_y - 1:crosshair_y + 1, :] = 180
        time.sleep(1.0 / max(self._config.fps, 1.0))
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

    def describe(self) -> str:
        c = self._config
        return (
            f"FAKE exposure={c.exposure_us}us fps={c.fps} gain={c.gain_db}dB "
            f"shape={self.frame_shape}"
        )
