# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — gui.settings                                      ║
# ║  « TOML persistence for the GUI preset »                         ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Reads ~/.config/ximea_tools/settings.toml on launch and         ║
# ║  writes it on quit.  Round-trips the CameraConfig and            ║
# ║  RecordingConfig field-by-field, with sane defaults when         ║
# ║  the file is missing or partial.                                 ║
# ╚══════════════════════════════════════════════════════════════════╝
"""TOML round-trip of CameraConfig + RecordingConfig + window state."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

from ..config import CameraConfig, RecordingConfig
from ..constants import (
    DEFAULT_EXPOSURE_US,
    DEFAULT_FPS,
    DEFAULT_GAIN_DB,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_ROI_OFFSET,
    SETTINGS_PATH,
)


@dataclass
class Settings:
    """In-memory representation of the GUI's persistent state."""

    camera:        CameraConfig
    recording:     RecordingConfig
    window_size:   tuple[int, int] = (1280, 800)
    histogram_hz:  float           = 5.0
    last_backend:  str             = "ximea"  # ximea | uvc | fake
    last_device:   str             = ""       # serial or "/dev/videoN"


# ┌────────────────────────────────────────────────────────────┐
# │ CameraConfig <-> dict                                      │
# └────────────────────────────────────────────────────────────┘
def _camera_to_dict(c: CameraConfig) -> dict:
    d: dict = {
        "exposure_us":  int(c.exposure_us),
        "fps":          float(c.fps),
        "gain_db":      float(c.gain_db),
        "roi_offset":   list(c.roi_offset),
        "trigger_mode": str(c.trigger_mode),
        "gpi_port":     int(c.gpi_port),
    }
    if c.roi_size is not None:
        d["roi_size"] = list(c.roi_size)
    if c.video_mode is not None:
        d["video_mode"] = list(c.video_mode)
    if c.serial is not None:
        d["serial"] = str(c.serial)
    return d


def _camera_from_dict(d: dict) -> CameraConfig:
    raw_size = d.get("roi_size")
    raw_mode = d.get("video_mode")
    return CameraConfig(
        exposure_us=int(d.get("exposure_us", DEFAULT_EXPOSURE_US)),
        fps=float(d.get("fps", DEFAULT_FPS)),
        gain_db=float(d.get("gain_db", DEFAULT_GAIN_DB)),
        roi_size=tuple(raw_size) if raw_size else None,
        roi_offset=tuple(d.get("roi_offset", DEFAULT_ROI_OFFSET)),
        video_mode=tuple(raw_mode) if raw_mode else None,
        trigger_mode=d.get("trigger_mode", "free_run"),
        gpi_port=int(d.get("gpi_port", 1)),
        serial=d.get("serial"),
    )


# ┌────────────────────────────────────────────────────────────┐
# │ RecordingConfig <-> dict                                   │
# └────────────────────────────────────────────────────────────┘
def _recording_to_dict(r: RecordingConfig) -> dict:
    d: dict = {
        "output_dir":      str(r.output_dir),
        "filename_prefix": str(r.filename_prefix),
        "filename_suffix": str(r.filename_suffix),
        "video_format":    str(r.video_format),
        "queue_size":      int(r.queue_size),
        "monochrome":      bool(r.monochrome),
    }
    if r.duration_s is not None:
        d["duration_s"] = float(r.duration_s)
    return d


def _recording_from_dict(d: dict) -> RecordingConfig:
    return RecordingConfig(
        output_dir=Path(d.get("output_dir", str(DEFAULT_OUTPUT_DIR))),
        duration_s=d.get("duration_s"),
        filename_prefix=d.get("filename_prefix", ""),
        filename_suffix=d.get("filename_suffix", ""),
        video_format=d.get("video_format", "mp4"),
        queue_size=int(d.get("queue_size", 30)),
        monochrome=bool(d.get("monochrome", False)),
    )


# ┌────────────────────────────────────────────────────────────┐
# │ load / save                                                │
# └────────────────────────────────────────────────────────────┘
def load_settings(path: Path = SETTINGS_PATH) -> Settings:
    """Return Settings from ``path`` or defaults if it does not exist."""
    if not path.exists():
        return Settings(camera=CameraConfig(), recording=RecordingConfig())
    with path.open("rb") as f:
        data = tomllib.load(f)
    cam = _camera_from_dict(data.get("camera", {}))
    rec = _recording_from_dict(data.get("recording", {}))
    win = data.get("window", {})
    sel = data.get("selection", {})
    size = tuple(win.get("size", (1280, 800)))
    return Settings(
        camera=cam,
        recording=rec,
        window_size=(int(size[0]), int(size[1])),
        histogram_hz=float(win.get("histogram_hz", 5.0)),
        last_backend=str(sel.get("backend", "ximea")),
        last_device=str(sel.get("device", "")),
    )


def save_settings(settings: Settings, path: Path = SETTINGS_PATH) -> None:
    """Write Settings to ``path``, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "camera":    _camera_to_dict(settings.camera),
        "recording": _recording_to_dict(settings.recording),
        "window": {
            "size":         list(settings.window_size),
            "histogram_hz": float(settings.histogram_hz),
        },
        "selection": {
            "backend": settings.last_backend,
            "device":  settings.last_device,
        },
    }
    with path.open("wb") as f:
        tomli_w.dump(data, f)
