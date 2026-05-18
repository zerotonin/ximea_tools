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
from .config import (
    CameraConfig,
    RecordingConfig,
    RecordingResult,
    parse_roi,
)
from .recorder import Recorder
from .writer import Mp4Writer

__all__ = [
    "__version__",
    "CameraConfig",
    "FrameMeta",
    "Mp4Writer",
    "Recorder",
    "RecordingConfig",
    "RecordingResult",
    "XimeaCamera",
    "parse_roi",
]
