"""Tests for PreviewWidget zoom/monochrome additions."""

from __future__ import annotations

import numpy as np


def test_zoom_default_is_fit(qtbot) -> None:  # type: ignore[no-untyped-def]
    from ximea_tools.gui.preview_widget import PreviewWidget

    w = PreviewWidget()
    qtbot.addWidget(w)
    assert w.zoom is None  # fit


def test_zoom_in_out_fit_cycle(qtbot) -> None:  # type: ignore[no-untyped-def]
    from ximea_tools.gui.preview_widget import PreviewWidget

    w = PreviewWidget()
    qtbot.addWidget(w)
    w.resize(640, 480)
    frame = np.zeros((100, 100), dtype=np.uint8)
    w.set_frame(frame)

    w.set_zoom(1.0)
    assert w.zoom == 1.0
    w.zoom_in()
    assert w.zoom > 1.0
    w.zoom_out()
    w.zoom_out()
    assert w.zoom < 1.0
    w.zoom_fit()
    assert w.zoom is None


def test_zoom_clamped(qtbot) -> None:  # type: ignore[no-untyped-def]
    from ximea_tools.gui.preview_widget import PreviewWidget

    w = PreviewWidget()
    qtbot.addWidget(w)
    w.set_zoom(1000.0)
    assert w.zoom <= 16.0
    w.set_zoom(0.0001)
    assert w.zoom >= 0.05


def test_monochrome_preview_collapses_bgr(qtbot) -> None:  # type: ignore[no-untyped-def]
    from PyQt5.QtGui import QImage

    from ximea_tools.gui.preview_widget import PreviewWidget, numpy_to_qimage

    w = PreviewWidget()
    qtbot.addWidget(w)
    bgr = np.full((20, 30, 3), [100, 150, 200], dtype=np.uint8)
    img_colour = numpy_to_qimage(bgr, monochrome=False)
    img_mono   = numpy_to_qimage(bgr, monochrome=True)
    assert img_colour.format() == QImage.Format_RGB888
    assert img_mono.format()   == QImage.Format_Grayscale8

    # Toggling on the widget should not raise.
    w.set_frame(bgr)
    w.set_monochrome(True)
    w.set_monochrome(False)
