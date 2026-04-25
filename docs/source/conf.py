"""Sphinx configuration — anno-save-analyzer docs．

furo テーマ + MyST (markdown) + autodoc + autodoc_pydantic + copybutton．
GitHub Pages 用の root URL は ``/anno-save-analyzer/`` を想定．
"""

from __future__ import annotations

import datetime as _dt
import os
import sys
from pathlib import Path

# -- Path setup -------------------------------------------------------------

_DOCS_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _DOCS_ROOT.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

# -- Project information ----------------------------------------------------

project = "anno-save-analyzer"
author = "Proletariat Yuuka"
copyright = f"{_dt.date.today().year}, {author}"

try:
    from importlib.metadata import version as _version

    release = _version("anno-save-analyzer")
except Exception:  # pragma: no cover - fallback for doc-only envs
    release = "0.5.0"
version = ".".join(release.split(".")[:2])

# -- General configuration --------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
    "sphinxcontrib.autodoc_pydantic",
    "myst_parser",
    "sphinx_copybutton",
    "sphinx_design",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

templates_path = ["_templates"]
exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    "ja/**",  # ja は ``make html-ja`` で別 build
]

# -- MyST -------------------------------------------------------------------

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "tasklist",
    "fieldlist",
    "attrs_inline",
    "substitution",
    "linkify",
]
myst_heading_anchors = 3

# -- autodoc / typehints ----------------------------------------------------

autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
    "undoc-members": True,
}
autodoc_typehints = "description"
autodoc_member_order = "bysource"
autodoc_preserve_defaults = True

# autodoc_pydantic — モデルをクリーンに表示
autodoc_pydantic_model_show_json = False
autodoc_pydantic_model_show_config_summary = False
autodoc_pydantic_model_show_validator_summary = False
autodoc_pydantic_model_show_field_summary = True

# -- intersphinx ------------------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pandas": ("https://pandas.pydata.org/docs/", None),
    "networkx": ("https://networkx.org/documentation/stable/", None),
}

# -- i18n -------------------------------------------------------------------

language = os.environ.get("SPHINX_LANGUAGE", "en")
locale_dirs = ["locales/"]
gettext_compact = False

# -- HTML -------------------------------------------------------------------

html_theme = "furo"
html_title = f"{project} {release}"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_theme_options = {
    "sidebar_hide_name": False,
    "source_repository": "https://github.com/yuuka-dev/anno-save-analyzer/",
    "source_branch": "main",
    "source_directory": "docs/source/",
    "light_css_variables": {
        "color-brand-primary": "#b02a30",
        "color-brand-content": "#b02a30",
    },
    "dark_css_variables": {
        "color-brand-primary": "#ff6b70",
        "color-brand-content": "#ff9ea2",
    },
}
