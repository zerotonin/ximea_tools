"""Regression: GUI must not crash when recording setup fails."""

from __future__ import annotations

from pathlib import Path

import pytest

from ximea_tools.config import CameraConfig, RecordingConfig


def test_start_recording_emits_error_on_unwritable_dir(qtbot, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A PermissionError from mkdir must reach the GUI as an error signal, not core-dump."""
    from ximea_tools.gui.camera_worker import CameraWorker

    def boom(*_args, **_kwargs):
        raise PermissionError("simulated: no write access")

    monkeypatch.setattr(Path, "mkdir", boom)

    cfg = CameraConfig(exposure_us=1_000, fps=100.0, roi_size=(64, 48))
    worker = CameraWorker(cfg, backend="fake")

    with qtbot.waitSignal(worker.started, timeout=2000):
        worker.start()

    bad_cfg = RecordingConfig(output_dir=tmp_path / "nope" / "deeper")

    with qtbot.waitSignal(worker.error, timeout=2000) as err:
        worker.start_recording(bad_cfg)

    assert "simulated" in err.args[0] or "Permission" in err.args[0]
    assert worker._recording is False  # noqa: SLF001 — regression check

    with qtbot.waitSignal(worker.stopped, timeout=2000):
        worker.stop()


def test_recording_dock_resets_button_on_state_change(qtbot) -> None:  # type: ignore[no-untyped-def]
    """on_recording_state_changed(False, '') must un-check the toggle."""
    from ximea_tools.gui.recording_dock import RecordingControlsDock

    dock = RecordingControlsDock()
    qtbot.addWidget(dock)
    dock.recordBtn.setChecked(True)
    dock.recordBtn.setText("■ Stop Recording")

    dock.on_recording_state_changed(False, "")
    assert dock.recordBtn.isChecked() is False
    assert "Start" in dock.recordBtn.text()
