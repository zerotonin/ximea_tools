"""Validation tests for CameraConfig, RecordingConfig, and parse_roi."""

from __future__ import annotations

from pathlib import Path

import pytest

from ximea_tools.config import (
    CameraConfig,
    RecordingConfig,
    parse_roi,
)


# ┌────────────────────────────────────────────────────────────┐
# │ CameraConfig                                               │
# └────────────────────────────────────────────────────────────┘
class TestCameraConfig:
    def test_defaults_are_valid(self) -> None:
        cfg = CameraConfig()
        assert cfg.exposure_us > 0
        assert cfg.fps > 0
        assert cfg.trigger_mode == "free_run"
        assert cfg.gpi_port == 1

    @pytest.mark.parametrize("bad", [-1, 0])
    def test_exposure_must_be_positive(self, bad: int) -> None:
        with pytest.raises(ValueError, match="exposure_us"):
            CameraConfig(exposure_us=bad)

    @pytest.mark.parametrize("bad", [-1.0, 0.0])
    def test_fps_must_be_positive(self, bad: float) -> None:
        with pytest.raises(ValueError, match="fps"):
            CameraConfig(fps=bad)

    def test_gain_cannot_be_negative(self) -> None:
        with pytest.raises(ValueError, match="gain_db"):
            CameraConfig(gain_db=-1.0)

    def test_roi_size_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="roi_size"):
            CameraConfig(roi_size=(0, 100))

    def test_roi_offset_must_be_nonneg(self) -> None:
        with pytest.raises(ValueError, match="roi_offset"):
            CameraConfig(roi_offset=(-1, 0))

    def test_gpi_port_must_be_1_or_2(self) -> None:
        with pytest.raises(ValueError, match="gpi_port"):
            CameraConfig(gpi_port=3)

    def test_is_frozen(self) -> None:
        cfg = CameraConfig()
        with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
            cfg.fps = 60.0  # type: ignore[misc]


# ┌────────────────────────────────────────────────────────────┐
# │ RecordingConfig                                            │
# └────────────────────────────────────────────────────────────┘
class TestRecordingConfig:
    def test_defaults_are_valid(self) -> None:
        cfg = RecordingConfig()
        assert cfg.duration_s is None
        assert cfg.queue_size > 0
        assert cfg.video_format == "mp4"

    def test_duration_must_be_positive_or_none(self) -> None:
        with pytest.raises(ValueError, match="duration_s"):
            RecordingConfig(duration_s=0)

    def test_queue_size_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="queue_size"):
            RecordingConfig(queue_size=0)

    def test_output_dir_is_a_path(self) -> None:
        cfg = RecordingConfig(output_dir=Path("/tmp/foo"))
        assert isinstance(cfg.output_dir, Path)


# ┌────────────────────────────────────────────────────────────┐
# │ parse_roi                                                  │
# └────────────────────────────────────────────────────────────┘
class TestParseRoi:
    def test_full_spec(self) -> None:
        size, off = parse_roi("1200x1000+424+44")
        assert size == (1200, 1000)
        assert off == (424, 44)

    def test_size_only(self) -> None:
        size, off = parse_roi("640x480")
        assert size == (640, 480)
        assert off == (0, 0)

    @pytest.mark.parametrize("bad", [
        "640", "640x", "640x480+", "640x480+10", "axb+1+2", "",
    ])
    def test_invalid_specs_raise(self, bad: str) -> None:
        with pytest.raises(ValueError, match="Invalid ROI"):
            parse_roi(bad)
