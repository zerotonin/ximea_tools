# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — __init__                                          ║
# ║  « package entry point — version, public API »                   ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Linux toolbox for XIMEA industrial cameras: a recorder,         ║
# ║  a PyQt5 GUI, and an external trigger (CueWire) integration.     ║
# ║                                                                  ║
# ║  Style: see ~/.claude/CLAUDE.md (Bart Geurten, U. Otago).        ║
# ╚══════════════════════════════════════════════════════════════════╝
"""ximea_tools — Linux toolbox for XIMEA industrial cameras."""

from __future__ import annotations

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "0.0.0+unknown"

from .camera import FrameMeta, XimeaCamera
from .capabilities import CameraCapabilities, Range, VideoMode
from .config import (
    CameraConfig,
    RecordingConfig,
    RecordingResult,
    parse_roi,
)
from .discovery import CameraInfo, list_all_cameras
from .recorder import Recorder, build_stem
from .uvc_camera import UvcCamera
from .writer import Mp4Writer

__all__ = [
    "__version__",
    "CameraCapabilities",
    "CameraConfig",
    "CameraInfo",
    "FrameMeta",
    "Mp4Writer",
    "Range",
    "Recorder",
    "RecordingConfig",
    "RecordingResult",
    "UvcCamera",
    "VideoMode",
    "XimeaCamera",
    "build_stem",
    "list_all_cameras",
    "parse_roi",
]
