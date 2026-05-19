"""ROI on UVC must crop in software (not change the device mode)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ximea_tools.config import CameraConfig

pytestmark = pytest.mark.skipif(
    not Path("/dev/video0").exists(),
    reason="no /dev/video0 (UVC) device available",
)


def test_uvc_software_roi_crops_frame() -> None:
    from ximea_tools.uvc_camera import UvcCamera

    cfg = CameraConfig(exposure_us=10_000, fps=15.0, roi_size=(120, 80), roi_offset=(10, 5))
    try:
        with UvcCamera(cfg, device_index=0) as cam:
            frame, _meta = cam.grab()
    except RuntimeError as e:
        pytest.skip(f"UVC unusable: {e}")

    assert frame.shape[:2] == (80, 120), (
        f"expected cropped (80, 120), got {frame.shape[:2]} — "
        "ROI shouldn't change the device mode"
    )


def test_uvc_full_frame_when_no_roi() -> None:
    from ximea_tools.uvc_camera import UvcCamera

    cfg = CameraConfig(exposure_us=10_000, fps=15.0)
    try:
        with UvcCamera(cfg, device_index=0) as cam:
            frame, _meta = cam.grab()
    except RuntimeError as e:
        pytest.skip(f"UVC unusable: {e}")

    assert frame.shape[0] > 0 and frame.shape[1] > 0
    assert cam.frame_shape == frame.shape[:2]
