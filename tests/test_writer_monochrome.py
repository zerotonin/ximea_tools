"""Tests for Mp4Writer monochrome mode (cv2-only with fallback)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ximea_tools.writer import Mp4Writer


def test_monochrome_round_trip(tmp_path: Path) -> None:
    out = tmp_path / "mono.mp4"
    shape = (100, 160)
    rng = np.random.default_rng(seed=7)
    frames = [rng.integers(0, 255, shape, dtype=np.uint8) for _ in range(20)]

    with Mp4Writer(out, fps=30.0, frame_shape=shape, queue_size=64, monochrome=True) as w:
        for f in frames:
            assert w.submit(f) is True

    assert out.exists()
    assert out.stat().st_size > 0

    cap = cv2.VideoCapture(str(out))
    n_read = 0
    try:
        while True:
            ok, _ = cap.read()
            if not ok:
                break
            n_read += 1
    finally:
        cap.release()

    assert n_read == 20


def test_monochrome_accepts_bgr_input(tmp_path: Path) -> None:
    """When fed a BGR frame, the writer converts to gray before encoding."""
    out = tmp_path / "mono_from_bgr.mp4"
    shape = (64, 64)
    bgr = np.full((*shape, 3), 200, dtype=np.uint8)

    with Mp4Writer(out, fps=30.0, frame_shape=shape, queue_size=8, monochrome=True) as w:
        for _ in range(5):
            assert w.submit(bgr) is True

    assert out.exists()
    assert out.stat().st_size > 0
