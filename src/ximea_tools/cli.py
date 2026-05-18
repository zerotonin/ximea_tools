# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — cli                                               ║
# ║  « argparse entry point for `ximea-record` »                     ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Parses CLI flags, builds CameraConfig and RecordingConfig,      ║
# ║  drives the Recorder with a tqdm progress bar, and prints a      ║
# ║  summary line on exit.                                           ║
# ╚══════════════════════════════════════════════════════════════════╝
"""argparse entry point for ``ximea-record``."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from pathlib import Path

from tqdm import tqdm

from .config import CameraConfig, RecordingConfig, parse_roi
from .constants import (
    DEFAULT_EXPOSURE_US,
    DEFAULT_FPS,
    DEFAULT_GAIN_DB,
    DEFAULT_OUTPUT_DIR,
)
from .recorder import Recorder


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ximea-record",
        description="Record a video from a XIMEA industrial camera.",
    )
    p.add_argument("--exposure", type=int, default=DEFAULT_EXPOSURE_US,
                   help="Exposure in microseconds (default: %(default)s).")
    p.add_argument("--fps", type=float, default=DEFAULT_FPS,
                   help="Frames per second (default: %(default)s).")
    p.add_argument("--gain", type=float, default=DEFAULT_GAIN_DB,
                   help="Gain in dB (default: %(default)s).")
    p.add_argument("--roi", type=str, default=None,
                   help="ROI as WxH[+X+Y], e.g. 1200x1000+424+44.")
    p.add_argument("--duration", type=float, default=None,
                   help="Recording duration in seconds; default: until SIGINT.")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR,
                   help="Output directory (default: %(default)s).")
    p.add_argument("--prefix", type=str, default="",
                   help="Filename prefix; timestamp is always appended.")
    p.add_argument("--trigger", choices=["free_run", "edge_rising", "edge_falling"],
                   default="free_run", help="External trigger mode.")
    p.add_argument("--gpi-port", type=int, choices=[1, 2], default=1,
                   help="XIMEA GPI port for the trigger (default: 1).")
    p.add_argument("--serial", type=str, default=None,
                   help="Camera serial number; default = first connected.")
    p.add_argument("--queue-size", type=int, default=30,
                   help="Writer thread frame buffer size (default: %(default)s).")
    p.add_argument("--no-progress", action="store_true",
                   help="Disable the tqdm progress bar.")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Enable INFO-level logging.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    )

    roi_size, roi_offset = (parse_roi(args.roi) if args.roi else (None, (0, 0)))

    cam_cfg = CameraConfig(
        exposure_us=args.exposure,
        fps=args.fps,
        gain_db=args.gain,
        roi_size=roi_size,
        roi_offset=roi_offset,
        trigger_mode=args.trigger,
        gpi_port=args.gpi_port,
        serial=args.serial,
    )
    rec_cfg = RecordingConfig(
        output_dir=args.output,
        duration_s=args.duration,
        filename_prefix=args.prefix,
        queue_size=args.queue_size,
    )
    recorder = Recorder(cam_cfg, rec_cfg)

    stop_flag = threading.Event()
    signal.signal(signal.SIGINT, lambda *_a: stop_flag.set())

    pbar = (
        tqdm(total=int(args.duration * args.fps), desc="Recording", unit="f")
        if not args.no_progress and args.duration is not None
        else None
    )

    def progress(done: int, _total: int | None) -> None:
        if pbar is not None:
            pbar.n = done
            pbar.refresh()

    try:
        result = recorder.run(progress=progress, stop_flag=stop_flag)
    finally:
        if pbar is not None:
            pbar.close()

    print(f"Video: {result.video_path}")
    print(f"Meta:  {result.meta_path}")
    print(
        f"Frames written: {result.frames_recorded}  "
        f"dropped: {result.frames_dropped}  "
        f"wall: {result.duration_s:.2f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
