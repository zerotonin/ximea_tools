"""Round-trip tests for ximea_tools.gui.settings."""

from __future__ import annotations

from pathlib import Path

from ximea_tools.config import CameraConfig, RecordingConfig
from ximea_tools.gui.settings import Settings, load_settings, save_settings


def test_load_returns_defaults_when_file_missing(tmp_path: Path) -> None:
    path = tmp_path / "nope.toml"
    s = load_settings(path)
    assert isinstance(s.camera, CameraConfig)
    assert isinstance(s.recording, RecordingConfig)


def test_round_trip_preserves_values(tmp_path: Path) -> None:
    path = tmp_path / "s.toml"
    cam = CameraConfig(
        exposure_us=12_345,
        fps=27.5,
        gain_db=3.5,
        roi_size=(640, 480),
        roi_offset=(100, 50),
        trigger_mode="edge_rising",
        gpi_port=2,
        serial="ABC123",
    )
    rec = RecordingConfig(
        output_dir=Path("/tmp/foo"),
        duration_s=42.0,
        filename_prefix="prefix_",
        queue_size=64,
    )
    s = Settings(camera=cam, recording=rec, window_size=(1024, 768), histogram_hz=8.0)

    save_settings(s, path)
    assert path.exists()

    loaded = load_settings(path)
    assert loaded.camera == cam
    assert loaded.recording == rec
    assert loaded.window_size == (1024, 768)
    assert loaded.histogram_hz == 8.0


def test_partial_file_uses_defaults_for_missing(tmp_path: Path) -> None:
    path = tmp_path / "partial.toml"
    path.write_text(
        '[camera]\nexposure_us = 7000\nfps = 12.0\n'
    )
    s = load_settings(path)
    assert s.camera.exposure_us == 7000
    assert s.camera.fps == 12.0
    assert s.camera.trigger_mode == "free_run"  # default
    assert s.recording.queue_size == 30  # default
