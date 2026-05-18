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
                       queue_size=rcfg.queue_size) as writer, \
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
        ts = datetime.now().strftime(FILENAME_TIMESTAMP_FORMAT)
        stem = f"{rcfg.filename_prefix}{ts}" if rcfg.filename_prefix else ts
        rcfg.output_dir.mkdir(parents=True, exist_ok=True)
        return (
            rcfg.output_dir / f"{stem}.mp4",
            rcfg.output_dir / f"{stem}.frames.csv",
        )
