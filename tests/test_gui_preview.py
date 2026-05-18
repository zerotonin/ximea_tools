"""pytest-qt smoke tests for PreviewWidget."""

from __future__ import annotations

import numpy as np
from PyQt5.QtCore import QPoint, Qt


def test_preview_accepts_gray_frame(qtbot) -> None:  # type: ignore[no-untyped-def]
    from ximea_tools.gui.preview_widget import PreviewWidget

    w = PreviewWidget()
    qtbot.addWidget(w)
    w.resize(640, 480)
    w.show()
    qtbot.waitExposed(w)

    frame = np.full((100, 100), 128, dtype=np.uint8)
    w.set_frame(frame)
    assert w._qimage is not None  # noqa: SLF001 — test introspection
    assert w._qimage.width() == 100
    assert w._qimage.height() == 100


def test_preview_emits_roi_on_drag(qtbot) -> None:  # type: ignore[no-untyped-def]
    from ximea_tools.gui.preview_widget import PreviewWidget

    w = PreviewWidget()
    qtbot.addWidget(w)
    w.resize(640, 480)
    w.show()
    qtbot.waitExposed(w)

    frame = np.zeros((200, 200), dtype=np.uint8)
    w.set_frame(frame)

    rois: list[tuple[int, int, int, int]] = []
    w.roiSelected.connect(lambda x, y, ww, hh: rois.append((x, y, ww, hh)))

    qtbot.mousePress(w, Qt.LeftButton, pos=QPoint(150, 100))
    qtbot.mouseMove(w, QPoint(400, 350))
    qtbot.mouseRelease(w, Qt.LeftButton, pos=QPoint(400, 350))

    assert len(rois) == 1
    x, y, ww, hh = rois[0]
    assert ww > 0 and hh > 0
    assert 0 <= x < 200 and 0 <= y < 200
    assert x + ww <= 200 and y + hh <= 200
