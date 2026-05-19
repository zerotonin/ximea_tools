"""Tests for v4l2-ctl output parsing (uses captured LifeCam Cinema output)."""

from __future__ import annotations

from ximea_tools.capabilities import (
    parse_v4l2_ctrls,
    parse_v4l2_formats,
)


# Real `v4l2-ctl --list-formats-ext` slice from the LifeCam (2026-05-20).
_LIFECAM_FORMATS = """\
ioctl: VIDIOC_ENUM_FMT
\tType: Video Capture

\t[0]: 'YUYV' (YUYV 4:2:2)
\t\tSize: Discrete 640x480
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t\t\tInterval: Discrete 0.050s (20.000 fps)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.100s (10.000 fps)
\t[1]: 'MJPG' (Motion-JPEG, compressed)
\t\tSize: Discrete 640x480
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.033s (30.000 fps)
"""

_LIFECAM_CTRLS = """\

User Controls

                     brightness 0x00980900 (int)    : min=30 max=255 step=1 default=133 value=133

Camera Controls

         exposure_time_absolute 0x009a0902 (int)    : min=5 max=20000 step=1 default=156 value=100
                           gain 0x00980913 (int)    : min=0 max=255 step=1 default=64 value=64
"""


def test_parse_formats_picks_up_resolutions() -> None:
    modes = parse_v4l2_formats(_LIFECAM_FORMATS)
    sizes = {(m.width, m.height) for m in modes}
    assert (640, 480) in sizes
    assert (1280, 720) in sizes
    # Two pixel formats × two sizes = 4 distinct VideoModes
    assert len(modes) == 4


def test_parse_formats_extracts_fps_options() -> None:
    modes = parse_v4l2_formats(_LIFECAM_FORMATS)
    yuyv_640 = next(m for m in modes if m.pixel_format == "YUYV" and m.width == 640)
    assert 30.0 in yuyv_640.fps_options
    assert 20.0 in yuyv_640.fps_options
    # fps_options should be sorted high→low
    assert yuyv_640.fps_options == tuple(sorted(yuyv_640.fps_options, reverse=True))


def test_parse_ctrls_finds_exposure_and_gain() -> None:
    ctrls = parse_v4l2_ctrls(_LIFECAM_CTRLS)
    assert "exposure_time_absolute" in ctrls
    assert "gain" in ctrls
    assert "brightness" in ctrls
    exp = ctrls["exposure_time_absolute"]
    assert exp.minimum == 5
    assert exp.maximum == 20000
    assert exp.step == 1


def test_parse_ctrls_handles_blank_input() -> None:
    assert parse_v4l2_ctrls("") == {}


def test_parse_formats_handles_blank_input() -> None:
    assert parse_v4l2_formats("") == ()
