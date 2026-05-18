"""Smoke tests for FakeCamera shape parity with XimeaCamera."""

from __future__ import annotations

import numpy as np

from ximea_tools.camera import FrameMeta
from ximea_tools.config import CameraConfig
from ximea_tools.gui.fake_camera import FakeCamera


def test_fake_camera_default_shape() -> None:
    cam = FakeCamera(CameraConfig(fps=100.0))
    with cam:
        frame, meta = cam.grab()
    assert frame.shape == (480, 640)
    assert frame.dtype == np.uint8
    assert isinstance(meta, FrameMeta)
    assert meta.acq_nframe == 0


def test_fake_camera_respects_roi_size() -> None:
    cam = FakeCamera(CameraConfig(fps=100.0, roi_size=(320, 240)))
    with cam:
        frame, _ = cam.grab()
    assert frame.shape == (240, 320)  # (H, W)
    assert cam.frame_shape == (240, 320)


def test_fake_camera_yields_via_generator() -> None:
    cam = FakeCamera(CameraConfig(fps=100.0))
    out = []
    with cam:
        for i, (frame, meta) in enumerate(cam.frames()):
            out.append((frame, meta))
            if i >= 2:
                break
    assert len(out) == 3
    assert [m.acq_nframe for _, m in out] == [0, 1, 2]
