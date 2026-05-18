"""Tests for Mp4Writer: synthetic frames round-trip and drop behaviour."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ximea_tools.writer import Mp4Writer


def test_writes_gray_frames_round_trip(tmp_path: Path) -> None:
    out = tmp_path / "synth.mp4"
    shape = (100, 160)  # (H, W)
    n_frames = 30
    rng = np.random.default_rng(seed=42)
    frames = [rng.integers(0, 255, shape, dtype=np.uint8) for _ in range(n_frames)]

    with Mp4Writer(out, fps=30.0, frame_shape=shape, queue_size=64) as writer:
        for f in frames:
            assert writer.submit(f) is True

    assert out.exists()
    assert out.stat().st_size > 0

    cap = cv2.VideoCapture(str(out))
    read_count = 0
    try:
        while True:
            ok, _ = cap.read()
            if not ok:
                break
            read_count += 1
    finally:
        cap.release()

    assert read_count == n_frames
    assert writer.frames_written == n_frames
    assert writer.frames_dropped == 0


def test_drops_when_queue_full(tmp_path: Path) -> None:
    out = tmp_path / "drop.mp4"
    shape = (32, 32)
    frame = np.zeros(shape, dtype=np.uint8)

    with Mp4Writer(out, fps=30.0, frame_shape=shape, queue_size=2) as writer:
        accepted = 0
        for _ in range(500):
            if writer.submit(frame):
                accepted += 1

    assert writer.frames_dropped > 0
    assert accepted + writer.frames_dropped == 500
