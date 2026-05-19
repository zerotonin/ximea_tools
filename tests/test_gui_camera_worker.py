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
