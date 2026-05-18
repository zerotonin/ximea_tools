"""Tests for XimeaCamera with a mocked ximea.xiapi module."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import numpy as np
import pytest

from ximea_tools.config import CameraConfig


@pytest.fixture
def fake_xiapi(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Inject a fake ``ximea.xiapi`` module into ``sys.modules``."""
    fake_cam = MagicMock(name="xiapi.Camera()")
    fake_cam.get_width.return_value = 1200
    fake_cam.get_height.return_value = 1000

    fake_img = MagicMock(name="xiapi.Image()")
    fake_img.acq_nframe = 0
    fake_img.tsSec = 0
    fake_img.tsUSec = 0
    fake_img.get_image_data_numpy.return_value = np.zeros(
        (1000, 1200), dtype=np.uint8,
    )

    fake_xiapi_mod = types.ModuleType("ximea.xiapi")
    fake_xiapi_mod.Camera = MagicMock(return_value=fake_cam)
    fake_xiapi_mod.Image = MagicMock(return_value=fake_img)

    fake_pkg = types.ModuleType("ximea")
    fake_pkg.xiapi = fake_xiapi_mod
    monkeypatch.setitem(sys.modules, "ximea", fake_pkg)
    monkeypatch.setitem(sys.modules, "ximea.xiapi", fake_xiapi_mod)
    return fake_xiapi_mod


def test_camera_opens_and_closes(fake_xiapi: MagicMock) -> None:
    from ximea_tools.camera import XimeaCamera

    cfg = CameraConfig(exposure_us=10_000, fps=30.0)
    with XimeaCamera(cfg) as cam:
        fake_cam = fake_xiapi.Camera.return_value
        fake_cam.open_device.assert_called_once()
        fake_cam.set_exposure.assert_called_once_with(10_000)
        fake_cam.set_framerate.assert_called_once_with(30.0)
        fake_cam.set_trigger_source.assert_called_once_with("XI_TRG_OFF")
        assert cam.frame_shape == (1000, 1200)
    fake_cam.close_device.assert_called_once()


def test_camera_open_by_serial(fake_xiapi: MagicMock) -> None:
    from ximea_tools.camera import XimeaCamera

    cfg = CameraConfig(serial="ABC123")
    with XimeaCamera(cfg):
        fake_cam = fake_xiapi.Camera.return_value
        fake_cam.open_device_by_SN.assert_called_once_with("ABC123")
        fake_cam.open_device.assert_not_called()


def test_camera_applies_roi(fake_xiapi: MagicMock) -> None:
    from ximea_tools.camera import XimeaCamera

    cfg = CameraConfig(roi_size=(640, 480), roi_offset=(100, 50))
    with XimeaCamera(cfg):
        fake_cam = fake_xiapi.Camera.return_value
        fake_cam.set_width.assert_called_once_with(640)
        fake_cam.set_height.assert_called_once_with(480)
        fake_cam.set_offsetX.assert_called_once_with(100)
        fake_cam.set_offsetY.assert_called_once_with(50)


def test_camera_applies_edge_trigger(fake_xiapi: MagicMock) -> None:
    from ximea_tools.camera import XimeaCamera

    cfg = CameraConfig(trigger_mode="edge_rising", gpi_port=2)
    with XimeaCamera(cfg):
        fake_cam = fake_xiapi.Camera.return_value
        fake_cam.set_trigger_source.assert_called_with("XI_TRG_EDGE_RISING")
        fake_cam.set_gpi_selector.assert_called_with("XI_GPI_PORT2")
        fake_cam.set_gpi_mode.assert_called_with("XI_GPI_TRIGGER")


def test_frames_yields_pairs(fake_xiapi: MagicMock) -> None:
    from ximea_tools.camera import FrameMeta, XimeaCamera

    fake_img = fake_xiapi.Image.return_value
    fake_img.get_image_data_numpy.return_value = np.zeros((100, 100), dtype=np.uint8)

    cfg = CameraConfig()
    with XimeaCamera(cfg) as cam:
        it = cam.frames()
        frame, meta = next(it)
        assert isinstance(frame, np.ndarray)
        assert isinstance(meta, FrameMeta)
        assert frame.shape == (100, 100)
