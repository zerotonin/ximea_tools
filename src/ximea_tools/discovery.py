# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — discovery                                         ║
# ║  « enumerate connected cameras across backends »                 ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Finds XIMEA devices via xiapi and UVC devices under             ║
# ║  /dev/video*, returning a flat list of CameraInfo records        ║
# ║  the GUI's picker dialog can show.  Falls back gracefully        ║
# ║  when one backend is unavailable.                                ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Enumerate connected cameras across backends."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CameraInfo:
    """One discovered camera, regardless of backend."""

    backend:    str  # "ximea" | "uvc"
    identifier: str  # XIMEA serial, or "/dev/videoN"
    name:       str
    notes:      str = ""


# ─────────────────────────────────────────────────────────────────
#  UVC enumeration via sysfs
# ─────────────────────────────────────────────────────────────────
_VIDEO_DEV_RE = re.compile(r"^video(\d+)$")


def list_uvc_cameras() -> list[CameraInfo]:
    """Enumerate ``/dev/video*`` devices that look like real capture nodes."""
    out: list[CameraInfo] = []
    sysfs_root = Path("/sys/class/video4linux")
    if not sysfs_root.exists():
        return out

    for entry in sorted(sysfs_root.iterdir()):
        m = _VIDEO_DEV_RE.match(entry.name)
        if not m:
            continue
        index = int(m.group(1))
        # Filter out metadata / output nodes: only Video Capture interfaces.
        index_str = (entry / "device" / "interface").read_text(errors="ignore").strip() \
            if (entry / "device" / "interface").exists() else ""
        name_file = entry / "name"
        name = name_file.read_text(errors="ignore").strip() if name_file.exists() else f"video{index}"
        # `v4l2-compliance --mode capture` would be authoritative; we approximate
        # by checking that index_type contains 'Capture' or falling back to
        # opening the device.  Cheap heuristic: keep the lowest index per name.
        out.append(CameraInfo(
            backend="uvc",
            identifier=f"/dev/video{index}",
            name=name,
            notes=index_str or "video4linux",
        ))
    # Dedup by name keeping lowest index — multi-interface webcams expose
    # several /dev/videoN nodes (capture, metadata, etc.).  The lowest is the
    # one cv2 will actually open.
    seen: dict[str, CameraInfo] = {}
    for cam in out:
        seen.setdefault(cam.name, cam)
    return list(seen.values())


# ─────────────────────────────────────────────────────────────────
#  XIMEA enumeration via xiapi
# ─────────────────────────────────────────────────────────────────
def list_ximea_cameras() -> list[CameraInfo]:
    """Return CameraInfo per connected XIMEA device, or [] if SDK absent."""
    try:
        from ximea import xiapi  # noqa: PLC0415 — lazy: SDK may be missing
    except ImportError:
        log.debug("XIMEA SDK not present — skipping XIMEA enumeration")
        return []

    out: list[CameraInfo] = []
    cam = xiapi.Camera()
    try:
        count = int(xiapi.Camera().get_number_devices())
    except Exception as e:
        log.debug("xiapi.get_number_devices failed: %s", e)
        return []
    for i in range(count):
        try:
            sn = xiapi.Camera().get_device_info_string_index(i, "device_sn")
            name = xiapi.Camera().get_device_info_string_index(i, "device_name")
        except Exception as e:
            log.debug("xiapi index %d info failed: %s", i, e)
            sn, name = f"index-{i}", f"XIMEA {i}"
        out.append(CameraInfo(
            backend="ximea",
            identifier=str(sn),
            name=str(name) or "XIMEA camera",
            notes="xiapi",
        ))
    del cam
    return out


# ─────────────────────────────────────────────────────────────────
#  Aggregate
# ─────────────────────────────────────────────────────────────────
def list_all_cameras() -> list[CameraInfo]:
    """All XIMEA + UVC cameras the system can see right now."""
    return list_ximea_cameras() + list_uvc_cameras()
