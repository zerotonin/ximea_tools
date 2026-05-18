# ╔══════════════════════════════════════════════════════════════════╗
# ║  ximea_tools — constants                                         ║
# ║  « one source of truth for colours, paths, defaults »            ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  Wong (2011) colourblind-safe palette, default camera            ║
# ║  settings, output path templates, and type aliases.              ║
# ║                                                                  ║
# ║  Import from here — never hardcode a magic number in a           ║
# ║  function body.                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Central configuration: colours, paths, defaults, type aliases."""

from __future__ import annotations

from pathlib import Path
from typing import TypeAlias

# ┌────────────────────────────────────────────────────────────┐
# │ Wong (2011) palette  « colourblind-safe base colours »     │
# └────────────────────────────────────────────────────────────┘
WONG: dict[str, str] = {
    "black":          "#000000",
    "orange":         "#E69F00",
    "sky_blue":       "#56B4E9",
    "bluish_green":   "#009E73",
    "yellow":         "#F0E442",
    "blue":           "#0072B2",
    "vermilion":      "#D55E00",
    "reddish_purple": "#CC79A7",
}

# ┌────────────────────────────────────────────────────────────┐
# │ Camera defaults  « XIMEA xiC industrial mono »             │
# └────────────────────────────────────────────────────────────┘
DEFAULT_EXPOSURE_US: int = 10_000       # 10 ms — safe starting point
DEFAULT_FPS: float = 30.0
DEFAULT_GAIN_DB: float = 0.0
DEFAULT_ROI_OFFSET: tuple[int, int] = (0, 0)
DEFAULT_ROI_SIZE: tuple[int, int] | None = None  # None = use full sensor

# ┌────────────────────────────────────────────────────────────┐
# │ Output paths  « keep recordings off the system drive »     │
# └────────────────────────────────────────────────────────────┘
DEFAULT_OUTPUT_DIR: Path = Path.home() / "ximea_recordings"
SETTINGS_PATH: Path = Path.home() / ".config" / "ximea_tools" / "settings.toml"
FILENAME_TIMESTAMP_FORMAT: str = "%Y-%m-%d_%H-%M-%S"

# ┌────────────────────────────────────────────────────────────┐
# │ Figure defaults  « SVG-first, editable text in Inkscape »  │
# └────────────────────────────────────────────────────────────┘
FIGURE_DPI: int = 200
FIGURE_FONT_FAMILY: str = "DejaVu Sans"

# ┌────────────────────────────────────────────────────────────┐
# │ Type aliases  « for readable signatures »                  │
# └────────────────────────────────────────────────────────────┘
FrameShape: TypeAlias = tuple[int, int]
RoiOffset:  TypeAlias = tuple[int, int]
RoiSize:    TypeAlias = tuple[int, int]
