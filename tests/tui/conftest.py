"""TUI テスト用フィクスチャ．"""

from __future__ import annotations

from pathlib import Path

import pytest

from anno_save_analyzer.trade import GameTitle, ItemDictionary
from anno_save_analyzer.tui.state import TuiState, load_state
from tests.trade.conftest import make_inner_filedb, wrap_as_outer


def _items(tmp_path: Path) -> ItemDictionary:
    title = "anno117"
    en = tmp_path / f"items_{title}.en.yaml"
    en.write_text(
        "100:\n  name: Wood\n  category: raw\n200:\n  name: Bricks\n",
        encoding="utf-8",
    )
    ja = tmp_path / f"items_{title}.ja.yaml"
    ja.write_text("100:\n  name: 木材\n200:\n  name: 煉瓦\n", encoding="utf-8")
    return ItemDictionary.load(GameTitle.ANNO_117, locales=["en", "ja"], data_dir=tmp_path)


@pytest.fixture
def tui_state(tmp_path: Path) -> TuiState:
    """サンプルセーブ無し，合成 inner FileDB を 2 セッション分作って state を組む．"""
    inner_a = make_inner_filedb(
        {
            "route": [(7, 100, 5, 0), (7, 200, -3, 0)],
            "passive": [(99, 100, 1, -10)],
        }
    )
    inner_b = make_inner_filedb(
        {"route": [(8, 200, 2, 0)]},
    )
    outer = wrap_as_outer([inner_a, inner_b])
    save = tmp_path / "fake.bin"
    save.write_bytes(outer)

    items = _items(tmp_path)
    return load_state(save, title=GameTitle.ANNO_117, locale="en", items=items)
