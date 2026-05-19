"""Tests for camera discovery — UVC enumeration."""

from __future__ import annotations

from pathlib import Path

import pytest

from ximea_tools.discovery import list_uvc_cameras


def test_list_uvc_cameras_returns_list() -> None:
    """Should always return a list, even when no devices are present."""
    result = list_uvc_cameras()
    assert isinstance(result, list)


@pytest.mark.skipif(
    not Path("/dev/video0").exists(),
    reason="no /dev/video0 (UVC) device available",
)
def test_list_uvc_cameras_finds_video0() -> None:
    cams = list_uvc_cameras()
    ids = {c.identifier for c in cams}
    assert "/dev/video0" in ids
    for c in cams:
        assert c.backend == "uvc"
        assert c.name
