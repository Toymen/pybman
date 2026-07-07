"""Sphinx configuration for the pybman documentation."""

import os
import sys

sys.path.insert(0, os.path.abspath("../.."))

from pybman import __version__

project = "pybman"
copyright = "2019 Donatus Herre, 2026 pybman contributors"
author = "Donatus Herre"
version = __version__
release = __version__

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "requests": ("https://requests.readthedocs.io/en/latest/", None),
}

autodoc_member_order = "bysource"
autodoc_typehints = "description"

exclude_patterns = []

html_theme = "alabaster"
html_theme_options = {
    "description": "Python client for MPG.PuRe (PubMan REST API)",
    "github_user": "Toymen",
    "github_repo": "pybman",
}
