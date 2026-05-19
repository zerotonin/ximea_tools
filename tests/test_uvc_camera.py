"""Smoke test for UvcCamera (skipped if no /dev/video0)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ximea_tools.config import CameraConfig

pytestmark = pytest.mark.skipif(
    not Path("/dev/video0").exists(),
    reason="no /dev/video0 (UVC) device available",
)


def test_uvc_camera_grabs_a_frame() -> None:
    from ximea_tools.uvc_camera import UvcCamera

    cfg = CameraConfig(exposure_us=10_000, fps=30.0)
    try:
        with UvcCamera(cfg, device_index=0) as cam:
            assert cam.frame_shape is not None
            frame, meta = cam.grab()
    except RuntimeError as e:
        pytest.skip(f"UVC device present but unusable: {e}")

    assert isinstance(frame, np.ndarray)
    assert frame.ndim == 3  # BGR
    assert frame.shape[2] == 3
    assert frame.dtype == np.uint8
    assert meta.acq_nframe == 0
