"""pytest-qt smoke test for CameraWorker against FakeCamera."""

from __future__ import annotations

import numpy as np
import pytest

from ximea_tools.config import CameraConfig


def test_camera_worker_emits_frames(qtbot) -> None:  # type: ignore[no-untyped-def]
    from ximea_tools.gui.camera_worker import CameraWorker

    cfg = CameraConfig(exposure_us=1_000, fps=100.0)
    worker = CameraWorker(cfg, backend="fake")

    frames = []
    worker.frameReady.connect(lambda f, m: frames.append((f, m)))

    with qtbot.waitSignal(worker.started, timeout=2000):
        worker.start()

    qtbot.waitUntil(lambda: len(frames) >= 3, timeout=3000)

    with qtbot.waitSignal(worker.stopped, timeout=3000):
        worker.stop()

    assert len(frames) >= 3
    for f, _m in frames:
        assert isinstance(f, np.ndarray)
        assert f.dtype == np.uint8


def test_camera_worker_records_on_request(qtbot, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from ximea_tools.config import RecordingConfig
    from ximea_tools.gui.camera_worker import CameraWorker

    cfg = CameraConfig(exposure_us=1_000, fps=100.0, roi_size=(64, 48))
    worker = CameraWorker(cfg, backend="fake")

    with qtbot.waitSignal(worker.started, timeout=2000):
        worker.start()

    rec_cfg = RecordingConfig(
        output_dir=tmp_path,
        duration_s=0.2,           # ~20 frames at 100 fps
        filename_prefix="rec_",
        queue_size=64,
    )
    with qtbot.waitSignal(worker.recordingStateChanged, timeout=3000) as bp:
        worker.start_recording(rec_cfg)
    assert bp.args[0] is True  # is_recording=True

    # Wait for recording to auto-stop at duration
    with qtbot.waitSignal(worker.recordingStateChanged, timeout=5000) as ap:
        pass
    assert ap.args[0] is False

    with qtbot.waitSignal(worker.stopped, timeout=3000):
        worker.stop()

    mp4s = list(tmp_path.glob("rec_*.mp4"))
    csvs = list(tmp_path.glob("rec_*.frames.csv"))
    assert len(mp4s) == 1 and mp4s[0].stat().st_size > 0
    assert len(csvs) == 1
    csv_text = csvs[0].read_text().strip().splitlines()
    assert csv_text[0] == "frame_idx,ts_host_s,ts_cam_s,acq_nframe"
    assert len(csv_text) >= 5  # header + several frames


def test_ring_buffer_arm_trigger_save(qtbot, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """End-to-end ring flow: arm, fill, trigger, file written."""
    from ximea_tools.config import RecordingConfig
    from ximea_tools.gui.camera_worker import CameraWorker

    cfg = CameraConfig(exposure_us=1_000, fps=100.0, roi_size=(64, 48))
    worker = CameraWorker(cfg, backend="fake")

    with qtbot.waitSignal(worker.started, timeout=2000):
        worker.start()

    rec_cfg = RecordingConfig(
        output_dir=tmp_path,
        filename_prefix="ring_",
        mode="ring_buffer",
        ring_pre_seconds=0.1,    # ~10 frames at 100 fps
        ring_post_seconds=0.05,  # ~5 frames
        queue_size=64,
    )

    with qtbot.waitSignal(worker.ringBufferStateChanged, timeout=3000) as armed:
        worker.arm_ring_buffer(rec_cfg)
    assert armed.args[0] == "armed"

    # Wait until the pre-buffer has caught at least 5 frames.
    qtbot.waitUntil(
        lambda: worker._ring is not None and worker._ring.fill_frames >= 5,  # noqa: SLF001
        timeout=3000,
    )

    # Triggering should ultimately produce an MP4 and a CSV.
    worker.trigger_ring_save()
    qtbot.waitUntil(lambda: worker._ring is None, timeout=5000)  # noqa: SLF001

    with qtbot.waitSignal(worker.stopped, timeout=3000):
        worker.stop()

    mp4s = list(tmp_path.glob("ring_*.mp4"))
    csvs = list(tmp_path.glob("ring_*.frames.csv"))
    assert len(mp4s) == 1 and mp4s[0].stat().st_size > 0
    assert len(csvs) == 1
    csv_lines = csvs[0].read_text().strip().splitlines()
    assert csv_lines[0] == "frame_idx,ts_host_s,ts_cam_s,acq_nframe"
    # header + at least the post tail
    assert len(csv_lines) >= 4


def test_timed_mode_auto_stops_by_wall_clock(qtbot, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Auto-stop must trigger on elapsed seconds, not frame count."""
    from ximea_tools.config import RecordingConfig
    from ximea_tools.gui.camera_worker import CameraWorker
    import time as _t

    cfg = CameraConfig(exposure_us=1_000, fps=100.0, roi_size=(48, 32))
    worker = CameraWorker(cfg, backend="fake")
    with qtbot.waitSignal(worker.started, timeout=2000):
        worker.start()

    rec_cfg = RecordingConfig(
        output_dir=tmp_path,
        mode="timed",
        duration_s=0.2,
        filename_prefix="timed_",
    )

    with qtbot.waitSignal(worker.recordingStateChanged, timeout=2000) as ev0:
        worker.start_recording(rec_cfg)
    assert ev0.args[0] is True
    t_start = _t.time()

    with qtbot.waitSignal(worker.recordingStateChanged, timeout=3000) as ev1:
        pass
    elapsed = _t.time() - t_start
    assert ev1.args[0] is False
    assert 0.15 <= elapsed <= 1.5, f"expected ~0.2s, got {elapsed:.2f}s"

    with qtbot.waitSignal(worker.stopped, timeout=2000):
        worker.stop()


def test_ring_buffer_disarm_drops_no_file(qtbot, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Arming then disarming must not create any output file."""
    from ximea_tools.config import RecordingConfig
    from ximea_tools.gui.camera_worker import CameraWorker

    cfg = CameraConfig(exposure_us=1_000, fps=100.0, roi_size=(32, 32))
    worker = CameraWorker(cfg, backend="fake")

    with qtbot.waitSignal(worker.started, timeout=2000):
        worker.start()

    rec_cfg = RecordingConfig(
        output_dir=tmp_path,
        filename_prefix="never_",
        mode="ring_buffer",
        ring_pre_seconds=0.1,
        ring_post_seconds=0.05,
    )

    with qtbot.waitSignal(worker.ringBufferStateChanged, timeout=3000):
        worker.arm_ring_buffer(rec_cfg)

    qtbot.waitUntil(
        lambda: worker._ring is not None and worker._ring.fill_frames >= 3,  # noqa: SLF001
        timeout=2000,
    )

    with qtbot.waitSignal(worker.recordingStateChanged, timeout=3000) as ev:
        worker.disarm_ring_buffer()
    assert ev.args[0] is False

    with qtbot.waitSignal(worker.stopped, timeout=3000):
        worker.stop()

    assert list(tmp_path.glob("never_*.mp4")) == []
    assert list(tmp_path.glob("never_*.frames.csv")) == []
