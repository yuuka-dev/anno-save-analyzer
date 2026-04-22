from pathlib import Path

from anno_save_analyzer.cli._title import resolve_title
from anno_save_analyzer.trade.models import GameTitle


def test_resolve_title_prefers_explicit_value() -> None:
    assert resolve_title(Path("save.a7s"), GameTitle.ANNO_117) is GameTitle.ANNO_117


def test_resolve_title_infers_from_extension_when_unspecified() -> None:
    assert resolve_title(Path("save.a7s"), None) is GameTitle.ANNO_1800
