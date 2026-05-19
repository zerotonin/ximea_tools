"""Tests for the recorder helpers — primarily build_stem permutations."""

from __future__ import annotations

from datetime import datetime

from ximea_tools.recorder import build_stem


REF = datetime(2026, 5, 20, 14, 30, 15)


def test_plain_timestamp_only() -> None:
    assert build_stem("", "", REF) == "2026-05-20__14-30-15"


def test_prefix_only() -> None:
    assert build_stem("rec", "", REF) == "rec_2026-05-20__14-30-15"


def test_suffix_only() -> None:
    assert build_stem("", "run2", REF) == "2026-05-20__14-30-15_run2"


def test_prefix_and_suffix() -> None:
    assert build_stem("rec", "run2", REF) == "rec_2026-05-20__14-30-15_run2"


def test_double_underscore_separates_date_and_time() -> None:
    stem = build_stem("", "", REF)
    # The "DATE__TIME" join is non-negotiable per Bart's spec.
    assert "__" in stem
    assert stem.count("__") == 1


def test_uses_datetime_now_when_ts_omitted() -> None:
    s = build_stem("a", "b")
    # Format is well-defined; just check shape.
    assert s.startswith("a_")
    assert s.endswith("_b")
    assert "__" in s
