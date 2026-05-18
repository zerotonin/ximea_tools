# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — writer                                            ║
# ║  « threaded MP4 writer with bounded queue »                      ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Frames are submitted from the camera thread and consumed        ║
# ║  by a dedicated writer thread.  When the queue is full the       ║
# ║  frame is dropped and a counter incremented — the camera         ║
# ║  thread is never blocked.                                        ║
# ║                                                                  ║
# ║  Fixes the legacy mp.Process(target=write(...)) bug by           ║
# ║  actually running the write off the main loop.                   ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Threaded MP4 writer with bounded queue."""

from __future__ import annotations

import logging
import queue
import threading
from pathlib import Path
from types import TracebackType

import cv2
import numpy as np

log = logging.getLogger(__name__)


class Mp4Writer:
    """Background MP4 writer fed by :meth:`submit`.

    Frames are queued and consumed by a daemon thread.  If the queue is
    full when ``submit`` is called the frame is dropped and a counter
    incremented — the camera loop is never blocked.

    Use as a context manager so :meth:`close` flushes the queue and
    releases the underlying ``cv2.VideoWriter``.
    """

    def __init__(
        self,
        path: Path,
        fps: float,
        frame_shape: tuple[int, int],
        queue_size: int = 30,
    ) -> None:
        self.path = Path(path)
        self.fps = fps
        self.frame_shape = frame_shape  # (H, W)
        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._thread: threading.Thread | None = None
        self._writer: cv2.VideoWriter | None = None
        self._stop = threading.Event()
        self.frames_written = 0
        self.frames_dropped = 0

    # ─── lifecycle ────────────────────────────────────────────────
    def __enter__(self) -> "Mp4Writer":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        h, w = self.frame_shape
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(
            str(self.path), fourcc, self.fps, (w, h), isColor=True,
        )
        if not self._writer.isOpened():
            raise RuntimeError(f"cv2.VideoWriter failed to open {self.path}")
        self._thread = threading.Thread(
            target=self._consume,
            name=f"Mp4Writer:{self.path.name}",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # ─── producer side ────────────────────────────────────────────
    def submit(self, frame: np.ndarray) -> bool:
        """Queue a frame for writing.  Return True if accepted, False if dropped."""
        try:
            self._queue.put_nowait(frame)
            return True
        except queue.Full:
            self.frames_dropped += 1
            return False

    # ─── consumer side (background thread) ────────────────────────
    def _consume(self) -> None:
        while not self._stop.is_set() or not self._queue.empty():
            try:
                frame = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if frame is None:
                self._queue.task_done()
                break
            self._write_one(frame)
            self._queue.task_done()

    def _write_one(self, frame: np.ndarray) -> None:
        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        self._writer.write(frame)
        self.frames_written += 1

    def close(self) -> None:
        """Flush the queue, stop the writer thread, release the file."""
        if self._thread is None:
            return
        self._stop.set()
        try:
            self._queue.put_nowait(None)  # wake consumer if blocked on get()
        except queue.Full:
            pass
        self._thread.join(timeout=10)
        if self._writer is not None:
            self._writer.release()
            self._writer = None
        log.info(
            "Mp4Writer closed: %s — wrote=%d dropped=%d",
            self.path, self.frames_written, self.frames_dropped,
        )
        self._thread = None
