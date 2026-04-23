"""``BalanceMainWindow`` の pytest-qt テスト．

WSL2 / Linux CI では ``QT_QPA_PLATFORM=offscreen`` で動く (conftest で setdefault)．
``pytest -m gui`` で走る．
"""

from __future__ import annotations

import dataclasses

import pytest

from anno_save_analyzer.trade.balance import (
    IslandBalance,
    ProductBalance,
    SupplyBalanceTable,
)
from anno_save_analyzer.trade.models import GameTitle

pytestmark = pytest.mark.gui


def _make_balance() -> SupplyBalanceTable:
    return SupplyBalanceTable(
        islands=(
            IslandBalance(
                area_manager="AM_1",
                city_name="岡山",
                resident_total=1000,
                products=(
                    ProductBalance(product_guid=200, produced_per_minute=5, consumed_per_minute=2),
                    ProductBalance(product_guid=300, produced_per_minute=1, consumed_per_minute=4),
                ),
            ),
            IslandBalance(
                area_manager="AM_NPC",
                city_name=None,
                resident_total=500,
                products=(
                    ProductBalance(product_guid=200, produced_per_minute=2, consumed_per_minute=1),
                ),
            ),
        )
    )


@pytest.fixture
def window(qtbot, tui_state):
    """合成 balance_table を注入した BalanceMainWindow．"""
    from anno_save_analyzer.gui.main_window import BalanceMainWindow

    state = dataclasses.replace(
        tui_state,
        title=GameTitle.ANNO_1800,
        balance_table=_make_balance(),
    )
    w = BalanceMainWindow(state)
    qtbot.addWidget(w)
    return w


def test_initial_population_shows_player_only(window) -> None:
    """初期 check はプレイヤー島のみ．AM_NPC は checked=False．"""
    lst = window._island_list
    player_checked = 0
    npc_checked = 0
    from PySide6.QtCore import Qt

    for i in range(lst.count()):
        item = lst.item(i)
        state = item.checkState()
        am = item.data(Qt.ItemDataRole.UserRole)
        if am == "AM_1" and state == Qt.CheckState.Checked:
            player_checked += 1
        elif am == "AM_NPC" and state == Qt.CheckState.Checked:
            npc_checked += 1
    assert player_checked == 1
    assert npc_checked == 0


def test_select_all_checks_every_island(window, qtbot) -> None:
    from PySide6.QtCore import Qt

    window._select_all()
    lst = window._island_list
    for i in range(lst.count()):
        assert lst.item(i).checkState() == Qt.CheckState.Checked


def test_select_none_empties_table(window) -> None:
    window._select_none()
    # 全 deselect → aggregate() は空 products
    assert window._table.rowCount() == 0


def test_table_rows_match_product_count(window) -> None:
    """プレイヤー島 (AM_1) のみ checked → 2 product．"""
    assert window._table.rowCount() == 2


def test_deficit_only_filters_rows(window, qtbot) -> None:
    """deficit_toggle を enable → delta 負の行だけ残る．"""
    window._deficit_toggle.setChecked(True)
    # Rum (guid=300) のみ (AM_1 のみ checked で delta = -3)
    assert window._table.rowCount() == 1
