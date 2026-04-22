"""CLI 向けの GameTitle 解決 helper."""

from __future__ import annotations

from pathlib import Path

from anno_save_analyzer.trade.models import GameTitle


def resolve_title(save: Path, explicit: GameTitle | None) -> GameTitle:
    """明示指定があればそれを使い，無ければ save 拡張子から推定する．"""
    if explicit is not None:
        return explicit
    return GameTitle.from_save_path(save)
