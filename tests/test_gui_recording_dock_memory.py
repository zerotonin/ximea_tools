"""Tests for the recording dock memory predictor and progress bars."""

from __future__ import annotations


def test_memory_label_reacts_to_pre_seconds(qtbot) -> None:  # type: ignore[no-untyped-def]
    from ximea_tools.gui.recording_dock import RecordingControlsDock

    dock = RecordingControlsDock()
    qtbot.addWidget(dock)

    dock.update_frame_context((480, 640), 30.0)
    dock.modeCombo.setCurrentIndex(dock.modeCombo.findData("ring_buffer"))

    dock.postSpin.setValue(0.0)  # isolate the pre-buffer in the prediction
    dock.preSpin.setValue(1.0)
    text_low = dock.memoryLabel.text()
    dock.preSpin.setValue(10.0)
    text_high = dock.memoryLabel.text()
    assert "predicted" in text_low and "predicted" in text_high
    mb_low  = int(text_low.split("≈")[1].split("MB")[0].strip())
    mb_high = int(text_high.split("≈")[1].split("MB")[0].strip())
    # 10× the pre-window should predict roughly 10× the memory.
    assert mb_high >= mb_low * 8


def test_memory_label_drops_when_monochrome(qtbot) -> None:  # type: ignore[no-untyped-def]
    from ximea_tools.gui.recording_dock import RecordingControlsDock

    dock = RecordingControlsDock()
    qtbot.addWidget(dock)

    dock.update_frame_context((480, 640), 30.0)
    dock.modeCombo.setCurrentIndex(dock.modeCombo.findData("ring_buffer"))
    dock.preSpin.setValue(2.0)

    dock.monochromeCheck.setChecked(False)
    bgr_text = dock.memoryLabel.text()
    dock.monochromeCheck.setChecked(True)
    mono_text = dock.memoryLabel.text()

    bgr_mb  = int(bgr_text.split("≈")[1].split("MB")[0].strip())
    mono_mb = int(mono_text.split("≈")[1].split("MB")[0].strip())
    # Mono is 1 channel vs 3 — should be roughly a third.
    assert mono_mb < bgr_mb
    assert mono_mb <= bgr_mb // 2 + 1


def test_progress_bars_max_track_frame_budget(qtbot) -> None:  # type: ignore[no-untyped-def]
    from ximea_tools.gui.recording_dock import RecordingControlsDock

    dock = RecordingControlsDock()
    qtbot.addWidget(dock)

    dock.update_frame_context((100, 100), 50.0)
    dock.modeCombo.setCurrentIndex(dock.modeCombo.findData("ring_buffer"))
    dock.preSpin.setValue(3.0)
    dock.postSpin.setValue(1.0)
    # 3.0 s × 50 fps = 150 frames pre, 1.0 s × 50 fps = 50 frames post.
    assert dock.preBar.maximum() == 150
    assert dock.postBar.maximum() == 50
