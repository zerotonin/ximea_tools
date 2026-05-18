"""Sphinx configuration for ximea_tools."""

from __future__ import annotations

import importlib.metadata
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

project = "ximea_tools"
author = "Bart R.H. Geurten"
copyright = "2026, Bart R.H. Geurten"

try:
    release = importlib.metadata.version("ximea_tools")
except importlib.metadata.PackageNotFoundError:
    release = "0.0.0+unknown"
version = ".".join(release.split(".")[:2])

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

autosummary_generate = True
napoleon_google_docstring = True
napoleon_numpy_docstring = False

autodoc_mock_imports = [
    "cv2",
    "ximea",
    "xiapi",
    "PyQt5",
    "serial",
    "tqdm",
    "numpy",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy":  ("https://numpy.org/doc/stable/", None),
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_static_path: list[str] = []
