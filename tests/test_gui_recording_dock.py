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


def test_mode_combo_swaps_stack_and_button_text(qtbot) -> None:  # type: ignore[no-untyped-def]
    from ximea_tools.gui.recording_dock import RecordingControlsDock

    dock = RecordingControlsDock()
    qtbot.addWidget(dock)

    # Default: free_run → stack page 0, button reads "Start Recording".
    assert dock.modeStack.currentIndex() == 0
    assert "Start Recording" in dock.recordBtn.text()
    assert dock.triggerBtn.isHidden() is True

    # Switch to ring_buffer → stack page 2, trigger button visible, recordBtn text changes.
    idx_ring = dock.modeCombo.findData("ring_buffer")
    dock.modeCombo.setCurrentIndex(idx_ring)
    assert dock.modeStack.currentIndex() == idx_ring
    assert "Arm" in dock.recordBtn.text()
    assert dock.triggerBtn.isHidden() is False

    # Switch to external → recordBtn disabled.
    idx_ext = dock.modeCombo.findData("external")
    dock.modeCombo.setCurrentIndex(idx_ext)
    assert dock.recordBtn.isEnabled() is False


def test_ring_buffer_config_fields_round_trip(qtbot) -> None:  # type: ignore[no-untyped-def]
    from ximea_tools.gui.recording_dock import RecordingControlsDock

    dock = RecordingControlsDock()
    qtbot.addWidget(dock)

    idx_ring = dock.modeCombo.findData("ring_buffer")
    dock.modeCombo.setCurrentIndex(idx_ring)
    dock.preSpin.setValue(7.5)
    dock.postSpin.setValue(1.5)
    dock.ramSpin.setValue(2048)

    cfg = dock.to_config()
    assert cfg.mode == "ring_buffer"
    assert cfg.ring_pre_seconds == 7.5
    assert cfg.ring_post_seconds == 1.5
    assert cfg.ring_max_ram_mb == 2048


def test_arm_emits_signal_in_ring_mode(qtbot) -> None:  # type: ignore[no-untyped-def]
    from ximea_tools.gui.recording_dock import RecordingControlsDock

    dock = RecordingControlsDock()
    qtbot.addWidget(dock)

    dock.modeCombo.setCurrentIndex(dock.modeCombo.findData("ring_buffer"))

    with qtbot.waitSignal(dock.armRingBufferRequested, timeout=500) as ev:
        dock.recordBtn.setChecked(True)
    cfg = ev.args[0]
    assert cfg.mode == "ring_buffer"
