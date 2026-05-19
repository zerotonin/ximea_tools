# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — capabilities                                      ║
# ║  « hardware capability introspection »                           ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  What ranges and discrete options does a camera actually         ║
# ║  accept?  Probes XIMEA via xiapi range queries and UVC via       ║
# ║  v4l2-ctl output; returns a CameraCapabilities the GUI can       ║
# ║  use to bound spinboxes and populate combo boxes.                ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Hardware capability introspection for XIMEA and UVC cameras."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Range:
    """Continuous numeric range with optional step (`step=0` means dense)."""

    minimum: float
    maximum: float
    step:    float = 0.0

    def clamp(self, value: float) -> float:
        return max(self.minimum, min(self.maximum, value))


@dataclass(frozen=True)
class VideoMode:
    """A discrete capture mode: resolution + pixel format + valid fps options."""

    width:        int
    height:       int
    pixel_format: str
    fps_options:  tuple[float, ...] = ()


@dataclass(frozen=True)
class CameraCapabilities:
    """What the camera will let us configure.

    Empty defaults are the safe answer for "we couldn't probe": the GUI
    falls back to free-form spinboxes with sensible bounds.
    """

    modes:                   tuple[VideoMode, ...] = ()
    exposure_us:             Range | None          = None
    gain_db:                 Range | None          = None
    fps:                     Range | None          = None
    supports_hardware_roi:   bool                  = False
    supports_hardware_trigger: bool                = False


# ─────────────────────────────────────────────────────────────────
#  UVC: parse `v4l2-ctl --list-formats-ext --device /dev/videoN`
# ─────────────────────────────────────────────────────────────────
_PIXFMT_RE   = re.compile(r"\['?(?P<code>[A-Z0-9]{4})'?\]:")
_SIZE_RE     = re.compile(r"Size:\s+Discrete\s+(\d+)x(\d+)")
_INTERVAL_RE = re.compile(r"Interval:.*\(([\d.]+)\s*fps\)")


def parse_v4l2_formats(text: str) -> tuple[VideoMode, ...]:
    """Parse the output of ``v4l2-ctl --list-formats-ext`` into VideoModes."""
    modes: dict[tuple[int, int, str], list[float]] = {}
    current_pixfmt: str | None = None
    current_size: tuple[int, int] | None = None

    for line in text.splitlines():
        # `[0]: 'YUYV' (...)` style header — capture the 4-char fourcc
        if "]:" in line and "'" in line:
            m = re.search(r"'(?P<code>[A-Z0-9]{4})'", line)
            if m:
                current_pixfmt = m.group("code")
                current_size = None
                continue
        m = _SIZE_RE.search(line)
        if m and current_pixfmt is not None:
            current_size = (int(m.group(1)), int(m.group(2)))
            modes.setdefault((*current_size, current_pixfmt), [])
            continue
        m = _INTERVAL_RE.search(line)
        if m and current_size is not None and current_pixfmt is not None:
            fps = float(m.group(1))
            key = (*current_size, current_pixfmt)
            modes.setdefault(key, []).append(fps)

    return tuple(
        VideoMode(w, h, fmt, tuple(sorted(set(fps_list), reverse=True)))
        for (w, h, fmt), fps_list in modes.items()
    )


# ─────────────────────────────────────────────────────────────────
#  UVC: parse `v4l2-ctl --list-ctrls`
# ─────────────────────────────────────────────────────────────────
_CTRL_RE = re.compile(
    r"^\s*(?P<name>[a-z_]+)\s+0x[0-9a-f]+\s+\(int\)\s*:"
    r"\s*min=(?P<min>-?\d+)\s+max=(?P<max>-?\d+)\s+step=(?P<step>\d+)"
)


def parse_v4l2_ctrls(text: str) -> dict[str, Range]:
    """Parse ``v4l2-ctl --list-ctrls`` into a name → Range mapping."""
    out: dict[str, Range] = {}
    for line in text.splitlines():
        m = _CTRL_RE.match(line)
        if not m:
            continue
        out[m.group("name")] = Range(
            minimum=float(m.group("min")),
            maximum=float(m.group("max")),
            step=float(m.group("step")),
        )
    return out


def _run_v4l2_ctl(device_path: str, *args: str) -> str | None:
    if shutil.which("v4l2-ctl") is None:
        return None
    try:
        result = subprocess.run(
            ["v4l2-ctl", "--device", device_path, *args],
            capture_output=True, text=True, timeout=3.0, check=False,
        )
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError) as e:
        log.debug("v4l2-ctl %s failed: %s", args, e)
        return None


def probe_uvc_capabilities(device_index: int) -> CameraCapabilities:
    """Probe a UVC camera at ``/dev/video{device_index}`` via v4l2-ctl."""
    device_path = f"/dev/video{device_index}"
    formats_out = _run_v4l2_ctl(device_path, "--list-formats-ext")
    ctrls_out   = _run_v4l2_ctl(device_path, "--list-ctrls")

    modes = parse_v4l2_formats(formats_out) if formats_out else ()
    ctrls = parse_v4l2_ctrls(ctrls_out) if ctrls_out else {}

    exposure: Range | None = None
    if "exposure_time_absolute" in ctrls:
        r = ctrls["exposure_time_absolute"]
        # v4l2 exposes the value in units of 100us.
        exposure = Range(r.minimum * 100, r.maximum * 100, r.step * 100)
    elif "exposure_absolute" in ctrls:
        r = ctrls["exposure_absolute"]
        exposure = Range(r.minimum * 100, r.maximum * 100, r.step * 100)

    gain: Range | None = None
    if "gain" in ctrls:
        gain = ctrls["gain"]  # already in raw units; webcam-specific scale

    return CameraCapabilities(
        modes=modes,
        exposure_us=exposure,
        gain_db=gain,
        fps=None,  # fps is per-mode on UVC, expressed in VideoMode.fps_options
        supports_hardware_roi=False,
        supports_hardware_trigger=False,
    )


# ─────────────────────────────────────────────────────────────────
#  XIMEA: query ranges via xiapi
# ─────────────────────────────────────────────────────────────────
def probe_ximea_capabilities(cam: object) -> CameraCapabilities:
    """Probe a XIMEA camera using xiapi range queries (best-effort)."""

    def _range(getter_min: str, getter_max: str, step_getter: str | None = None) -> Range | None:
        try:
            lo = float(getattr(cam, getter_min)())
            hi = float(getattr(cam, getter_max)())
            st = float(getattr(cam, step_getter)()) if step_getter else 0.0
            return Range(lo, hi, st)
        except Exception as e:
            log.debug("xiapi range query %s/%s failed: %s", getter_min, getter_max, e)
            return None

    modes: tuple[VideoMode, ...] = ()
    try:
        max_w = int(cam.get_width_maximum())
        max_h = int(cam.get_height_maximum())
        modes = (VideoMode(max_w, max_h, "MONO8"),)
    except Exception as e:
        log.debug("xiapi sensor-size query failed: %s", e)

    return CameraCapabilities(
        modes=modes,
        exposure_us=_range("get_exposure_minimum", "get_exposure_maximum", "get_exposure_increment"),
        gain_db    =_range("get_gain_minimum",     "get_gain_maximum",     "get_gain_increment"),
        fps        =_range("get_framerate_minimum", "get_framerate_maximum"),
        supports_hardware_roi=True,
        supports_hardware_trigger=True,
    )
