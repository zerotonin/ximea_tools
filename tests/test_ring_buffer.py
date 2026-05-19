"""Unit tests for the RingBuffer pre+post helper."""

from __future__ import annotations

import numpy as np

from ximea_tools.camera import FrameMeta
from ximea_tools.recorder import RingBuffer


def _meta(idx: int) -> FrameMeta:
    return FrameMeta(acq_nframe=idx, ts_host_s=float(idx), ts_cam_s=float(idx))


def _frame(idx: int, shape=(8, 8)) -> np.ndarray:
    return np.full(shape, idx & 0xFF, dtype=np.uint8)


def test_pre_buffer_evicts_old_frames() -> None:
    ring = RingBuffer(pre_seconds=1.0, post_seconds=0.0, fps=10.0,
                      frame_shape=(8, 8), bytes_per_pix=1)
    assert ring.pre_frames == 10
    for i in range(25):
        ring.push(_frame(i), _meta(i))
    # Only the most recent 10 should remain.
    assert ring.fill_frames == 10
    pre = [m.acq_nframe for _, m in ring.frames()]
    assert pre == list(range(15, 25))


def test_trigger_collects_post_frames_then_done() -> None:
    ring = RingBuffer(pre_seconds=0.5, post_seconds=0.3, fps=10.0,
                      frame_shape=(4, 4), bytes_per_pix=1)
    assert ring.pre_frames == 5
    assert ring.post_frames == 3
    # Fill pre buffer
    for i in range(7):
        ring.push(_frame(i), _meta(i))
    assert ring.state == "armed"
    assert ring.fill_frames == 5

    ring.trigger()
    assert ring.state == "post"
    # Three post-trigger frames complete the recording
    for i in range(7, 10):
        ring.push(_frame(i), _meta(i))
    assert ring.state == "done"
    # 5 pre + 3 post, in order
    indices = [m.acq_nframe for _, m in ring.frames()]
    assert indices == [2, 3, 4, 5, 6, 7, 8, 9]


def test_post_zero_goes_straight_to_done() -> None:
    ring = RingBuffer(pre_seconds=0.5, post_seconds=0.0, fps=10.0,
                      frame_shape=(4, 4), bytes_per_pix=1)
    for i in range(5):
        ring.push(_frame(i), _meta(i))
    ring.trigger()
    assert ring.state == "done"


def test_ram_cap_clamps_pre_frames() -> None:
    # 1000×1000 BGR @ 200 fps × 10s = 6 GB requested; cap at 256 MB.
    ring = RingBuffer(pre_seconds=10.0, post_seconds=1.0, fps=200.0,
                      frame_shape=(1000, 1000), bytes_per_pix=3,
                      max_ram_mb=256)
    # 256 MB / (1_000_000 × 3) = 85 frames
    assert ring.pre_frames == 85
    assert ring.pre_frames_clamped is True


def test_unclamped_when_within_budget() -> None:
    ring = RingBuffer(pre_seconds=1.0, post_seconds=0.5, fps=30.0,
                      frame_shape=(640, 480), bytes_per_pix=3,
                      max_ram_mb=1024)
    assert ring.pre_frames == 30
    assert ring.pre_frames_clamped is False


def test_frames_are_copied_not_aliased() -> None:
    ring = RingBuffer(pre_seconds=0.5, post_seconds=0.0, fps=10.0,
                      frame_shape=(4, 4), bytes_per_pix=1)
    f = _frame(0)
    ring.push(f, _meta(0))
    f[:] = 42  # mutate after push
    stored = next(iter(ring.frames()))[0]
    assert int(stored[0, 0]) == 0  # not 42 — the buffer made a copy
