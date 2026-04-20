"""tui.theme のテスト．"""

from __future__ import annotations

from anno_save_analyzer.tui.theme import (
    DEFAULT_CSS,
    USSR_CSS,
    USSR_TITLE_PREFIX,
    theme_css,
)


def test_default_theme_resolves_to_default_css() -> None:
    assert theme_css("default") == DEFAULT_CSS


def test_ussr_theme_resolves_to_ussr_css() -> None:
    assert theme_css("ussr") == USSR_CSS


def test_unknown_theme_falls_back_to_default() -> None:
    assert theme_css("totally-made-up") == DEFAULT_CSS


def test_ussr_title_prefix_contains_sickle_and_hammer() -> None:
    assert "☭" in USSR_TITLE_PREFIX
