"""Smoke tests: package imports cleanly and exposes a version and palette."""

from __future__ import annotations

import importlib


def test_package_imports() -> None:
    pkg = importlib.import_module("ximea_tools")
    assert hasattr(pkg, "__version__")
    assert isinstance(pkg.__version__, str)
    assert pkg.__version__ != ""


def test_constants_wong_palette() -> None:
    from ximea_tools.constants import WONG

    expected = {
        "black", "orange", "sky_blue", "bluish_green",
        "yellow", "blue", "vermilion", "reddish_purple",
    }
    assert set(WONG) == expected
    for hex_code in WONG.values():
        assert hex_code.startswith("#")
        assert len(hex_code) == 7
        int(hex_code[1:], 16)  # raises if not valid hex


def test_constants_defaults_sane() -> None:
    from ximea_tools.constants import (
        DEFAULT_EXPOSURE_US,
        DEFAULT_FPS,
        DEFAULT_GAIN_DB,
        DEFAULT_ROI_OFFSET,
    )

    assert DEFAULT_EXPOSURE_US > 0
    assert DEFAULT_FPS > 0
    assert DEFAULT_GAIN_DB >= 0
    assert len(DEFAULT_ROI_OFFSET) == 2
