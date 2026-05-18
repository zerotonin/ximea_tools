# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — config                                            ║
# ║  « frozen dataclasses for camera and recording settings »        ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Validated at construction (CLI boundary).  No business logic    ║
# ║  lives here — these are pure data carriers consumed by the       ║
# ║  camera, writer, and recorder.                                   ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Frozen dataclasses for camera and recording settings."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .constants import (
    DEFAULT_EXPOSURE_US,
    DEFAULT_FPS,
    DEFAULT_GAIN_DB,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_ROI_OFFSET,
    DEFAULT_ROI_SIZE,
    RoiOffset,
    RoiSize,
)

TriggerMode = Literal["free_run", "edge_rising", "edge_falling"]
VideoFormat = Literal["mp4"]


@dataclass(frozen=True)
class CameraConfig:
    """Camera-side settings, validated at construction."""

    exposure_us:  int               = DEFAULT_EXPOSURE_US
    fps:          float             = DEFAULT_FPS
    gain_db:      float             = DEFAULT_GAIN_DB
    roi_size:     RoiSize | None    = DEFAULT_ROI_SIZE
    roi_offset:   RoiOffset         = DEFAULT_ROI_OFFSET
    trigger_mode: TriggerMode       = "free_run"
    gpi_port:     int               = 1
    serial:       str | None        = None  # None = first connected camera

    def __post_init__(self) -> None:
        if self.exposure_us <= 0:
            raise ValueError(f"exposure_us must be > 0, got {self.exposure_us}")
        if self.fps <= 0:
            raise ValueError(f"fps must be > 0, got {self.fps}")
        if self.gain_db < 0:
            raise ValueError(f"gain_db must be >= 0, got {self.gain_db}")
        if self.roi_size is not None and any(s <= 0 for s in self.roi_size):
            raise ValueError(f"roi_size must be positive, got {self.roi_size}")
        if any(o < 0 for o in self.roi_offset):
            raise ValueError(f"roi_offset must be non-negative, got {self.roi_offset}")
        if self.gpi_port not in (1, 2):
            raise ValueError(f"gpi_port must be 1 or 2, got {self.gpi_port}")


@dataclass(frozen=True)
class RecordingConfig:
    """Recording-side settings: where to write, for how long."""

    output_dir:      Path        = DEFAULT_OUTPUT_DIR
    duration_s:      float | None = None  # None = run until stop_flag / SIGINT
    filename_prefix: str         = ""
    video_format:    VideoFormat = "mp4"
    queue_size:      int         = 30      # writer thread buffer

    def __post_init__(self) -> None:
        if self.duration_s is not None and self.duration_s <= 0:
            raise ValueError(f"duration_s must be > 0 or None, got {self.duration_s}")
        if self.queue_size <= 0:
            raise ValueError(f"queue_size must be > 0, got {self.queue_size}")


@dataclass(frozen=True)
class RecordingResult:
    """Summary of a completed recording."""

    video_path:      Path
    meta_path:       Path
    frames_recorded: int
    frames_dropped:  int
    duration_s:      float


_ROI_RE = re.compile(r"^(\d+)x(\d+)(?:\+(\d+)\+(\d+))?$")


def parse_roi(spec: str) -> tuple[RoiSize, RoiOffset]:
    """Parse a ROI spec like ``1200x1000+424+44`` or ``1200x1000``.

    Returns:
        ``((width, height), (x, y))``.  Offset defaults to ``(0, 0)``
        when omitted.

    Raises:
        ValueError: if ``spec`` does not match ``WxH[+X+Y]``.
    """
    m = _ROI_RE.match(spec)
    if not m:
        raise ValueError(
            f"Invalid ROI spec {spec!r}; expected WxH+X+Y (e.g. 1200x1000+424+44)"
        )
    w, h = int(m.group(1)), int(m.group(2))
    x, y = (int(m.group(3)), int(m.group(4))) if m.group(3) is not None else (0, 0)
    return (w, h), (x, y)
