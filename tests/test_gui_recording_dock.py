"""Tests for the recording dock — suffix field and live example label."""

from __future__ import annotations


def test_example_label_updates_when_prefix_changes(qtbot) -> None:  # type: ignore[no-untyped-def]
    from ximea_tools.gui.recording_dock import RecordingControlsDock

    dock = RecordingControlsDock()
    qtbot.addWidget(dock)

    dock.prefixEdit.setText("rec")
    text = dock.exampleLabel.text()
    assert text.startswith("rec_")
    assert text.endswith(".mp4")
    assert "__" in text


def test_example_label_includes_suffix(qtbot) -> None:  # type: ignore[no-untyped-def]
    from ximea_tools.gui.recording_dock import RecordingControlsDock

    dock = RecordingControlsDock()
    qtbot.addWidget(dock)

    dock.suffixEdit.setText("run2")
    text = dock.exampleLabel.text()
    # date-time block + _run2.mp4
    assert text.endswith("_run2.mp4")


def test_to_config_round_trips_suffix_and_monochrome(qtbot) -> None:  # type: ignore[no-untyped-def]
    from ximea_tools.gui.recording_dock import RecordingControlsDock

    dock = RecordingControlsDock()
    qtbot.addWidget(dock)

    dock.prefixEdit.setText("p")
    dock.suffixEdit.setText("s")
    dock.monochromeCheck.setChecked(True)

    cfg = dock.to_config()
    assert cfg.filename_prefix == "p"
    assert cfg.filename_suffix == "s"
    assert cfg.monochrome is True
