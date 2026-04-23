"""GUI test 用 pytest-qt setup + fixture．

Linux (WSL2) で Display が無くても pytest-qt が offscreen platform で起動
できるよう環境変数を強制する．Windows CI runner では wayland/windows
platform が自動選択されるため無害．

PySide6 が install されていない環境 (通常の CI pytest job) では
``test_main_window.py`` の collection を skip する．``pytest -m gui`` を
走らせるなら ``pip install -e .[gui]`` で PySide6 を入れてから．
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# PySide6 未 install 環境では QMainWindow を使う test_main_window.py を除外．
# viewmodels は Qt 非依存なのでそのまま collection 通せる．
if importlib.util.find_spec("PySide6") is None:
    collect_ignore_glob = ["test_main_window.py"]

from anno_save_analyzer.trade import GameTitle, ItemDictionary  # noqa: E402
from anno_save_analyzer.tui.state import TuiState, load_state  # noqa: E402
from tests.trade.conftest import make_inner_filedb, wrap_as_outer  # noqa: E402


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
    """GUI window の元になる合成 TuiState．TUI 層の同名 fixture と同等．"""
    inner_a = make_inner_filedb(
        {
            "route": [(7, 100, 5, 0), (7, 200, -3, 0)],
            "passive": [(99, 100, 1, -10)],
        }
    )
    inner_b = make_inner_filedb({"route": [(8, 200, 2, 0)]})
    outer = wrap_as_outer([inner_a, inner_b])
    save = tmp_path / "fake.bin"
    save.write_bytes(outer)

    items = _items(tmp_path)
    return load_state(save, title=GameTitle.ANNO_117, locale="en", items=items)
