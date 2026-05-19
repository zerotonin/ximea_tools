# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — recorder                                          ║
# ║  « orchestrates camera, writer, and sidecar CSV »                ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Composes XimeaCamera + Mp4Writer and writes a frames CSV        ║
# ║  (ts_host_s, ts_cam_s, acq_nframe) alongside the video for       ║
# ║  downstream synchronisation and dropped-frame detection.         ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Orchestrate camera, writer, and sidecar CSV."""

from __future__ import annotations

import csv
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from .camera import XimeaCamera
from .config import CameraConfig, RecordingConfig, RecordingResult
from .constants import FILENAME_TIMESTAMP_FORMAT
from .writer import Mp4Writer

log = logging.getLogger(__name__)

ProgressCb = Callable[[int, "int | None"], None]


def build_stem(prefix: str, suffix: str, ts: datetime | None = None) -> str:
    """Build a recording filename stem.

    Format: ``{prefix_}YYYY-MM-DD__HH-MM-SS{_suffix}`` where the brace
    parts are omitted when ``prefix`` or ``suffix`` is empty.  The
    timestamp uses :data:`ximea_tools.constants.FILENAME_TIMESTAMP_FORMAT`.
    """
    if ts is None:
        ts = datetime.now()
    date_str = ts.strftime(FILENAME_TIMESTAMP_FORMAT)
    p = f"{prefix}_" if prefix else ""
    s = f"_{suffix}" if suffix else ""
    return f"{p}{date_str}{s}"


# ─────────────────────────────────────────────────────────────────
#  Ring buffer  «  pre-trigger memory + post-trigger capture  »
# ─────────────────────────────────────────────────────────────────
class RingBuffer:
    """Fixed-capacity pre-trigger buffer with a configurable post-trigger tail.

    Lifecycle:

    1. **ARMED** — every pushed frame goes into a ``collections.deque``
       with ``maxlen = pre_frames``.  Older frames are evicted.
    2. **POST** — after :meth:`trigger`, the next ``post_frames`` pushes
       are appended to a separate list (no eviction).
    3. **DONE** — the post-tail is full; :meth:`frames` iterates the
       concatenation in time order, oldest first.

    A RAM cap clamps the pre-buffer at construction time so a high
    framerate × long pre-window doesn't OOM the lab workstation.
    """

    def __init__(
        self,
        pre_seconds:   float,
        post_seconds:  float,
        fps:           float,
        frame_shape:   tuple[int, int],
        bytes_per_pix: int = 3,
        max_ram_mb:    int = 1024,
    ) -> None:
        from collections import deque  # noqa: PLC0415 — kept lazy for clarity

        self.fps = fps
        h, w = frame_shape
        bytes_per_frame = max(1, h * w * bytes_per_pix)
        wanted_pre  = int(pre_seconds  * fps)
        wanted_post = int(post_seconds * fps)
        cap_frames  = max(1, int((max_ram_mb * 1_000_000) / bytes_per_frame))
        self.pre_frames        = min(wanted_pre,  cap_frames)
        self.post_frames       = min(wanted_post, cap_frames)
        self.pre_frames_clamped = self.pre_frames < wanted_pre
        self._deque: deque = deque(maxlen=self.pre_frames)
        self._post: list = []
        self._post_remaining = 0
        self._state: str = "armed"

    # ─── state ────────────────────────────────────────────────────
    @property
    def state(self) -> str:
        return self._state

    @property
    def fill_frames(self) -> int:
        return len(self._deque)

    @property
    def fill_seconds(self) -> float:
        return self.fill_frames / max(self.fps, 1e-6)

    @property
    def total_frames(self) -> int:
        return len(self._deque) + len(self._post)

    # ─── transitions ──────────────────────────────────────────────
    def push(self, frame, meta) -> str:
        """Append a frame in the current state; return new state."""
        if self._state == "armed":
            self._deque.append((frame.copy(), meta))
        elif self._state == "post":
            self._post.append((frame.copy(), meta))
            self._post_remaining -= 1
            if self._post_remaining <= 0:
                self._state = "done"
        return self._state

    def trigger(self) -> None:
        """Switch from armed to post-capturing; no-op if not armed."""
        if self._state == "armed":
            self._post_remaining = self.post_frames
            if self.post_frames == 0:
                self._state = "done"
            else:
                self._state = "post"

    def frames(self):
        """Iterate ``(frame, meta)`` in time order — pre buffer, then post."""
        for fm in self._deque:
            yield fm
        for fm in self._post:
            yield fm


class Recorder:
    """High-level: open camera, stream frames into writer + CSV, return summary."""

    def __init__(
        self,
        camera_cfg: CameraConfig,
        recording_cfg: RecordingConfig,
    ) -> None:
        self.camera_cfg = camera_cfg
        self.recording_cfg = recording_cfg

    def run(
        self,
        progress: ProgressCb | None = None,
        stop_flag: threading.Event | None = None,
    ) -> RecordingResult:
        """Record until ``duration_s`` elapses or ``stop_flag`` is set."""
        ccfg = self.camera_cfg
        rcfg = self.recording_cfg
        video_path, meta_path = self._paths()
        max_frames = (
            int(rcfg.duration_s * ccfg.fps)
            if rcfg.duration_s is not None else None
        )
        t_start = time.time()

        with XimeaCamera(ccfg) as cam, \
             Mp4Writer(video_path, ccfg.fps, cam.frame_shape,
                       queue_size=rcfg.queue_size,
                       monochrome=rcfg.monochrome) as writer, \
             meta_path.open("w", newline="") as meta_f:

            csv_writer = csv.writer(meta_f)
            csv_writer.writerow(["frame_idx", "ts_host_s", "ts_cam_s", "acq_nframe"])

            log.info("Recording start — %s -> %s", cam.describe(), video_path)
            for idx, (frame, meta) in enumerate(cam.frames()):
                if max_frames is not None and idx >= max_frames:
                    break
                if stop_flag is not None and stop_flag.is_set():
                    log.info("Stop requested at frame %d", idx)
                    break
                writer.submit(frame)
                csv_writer.writerow([idx, meta.ts_host_s, meta.ts_cam_s, meta.acq_nframe])
                if progress is not None:
                    progress(idx + 1, max_frames)

        result = RecordingResult(
            video_path=video_path,
            meta_path=meta_path,
            frames_recorded=writer.frames_written,
            frames_dropped=writer.frames_dropped,
            duration_s=time.time() - t_start,
        )
        log.info(
            "Recording done — %d written, %d dropped, %.2fs wall",
            result.frames_recorded, result.frames_dropped, result.duration_s,
        )
        return result

    # ─── helpers ──────────────────────────────────────────────────
    def _paths(self) -> tuple[Path, Path]:
        rcfg = self.recording_cfg
        stem = build_stem(rcfg.filename_prefix, rcfg.filename_suffix)
        rcfg.output_dir.mkdir(parents=True, exist_ok=True)
        return (
            rcfg.output_dir / f"{stem}.mp4",
            rcfg.output_dir / f"{stem}.frames.csv",
        )
