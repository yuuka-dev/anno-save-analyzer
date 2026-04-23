"""Supply Balance screen の Pilot ベース UI テスト．

合成 ``SupplyBalanceTable`` を ``TuiState`` に注入して ``TradeApp`` を起動し，
画面遷移 / DataTable の行数 / deficit-only toggle を確認する．
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from anno_save_analyzer.trade.balance import (
    IslandBalance,
    ProductBalance,
    SupplyBalanceTable,
)
from anno_save_analyzer.trade.models import GameTitle
from anno_save_analyzer.tui.app import TradeApp
from anno_save_analyzer.tui.screens import SupplyBalanceScreen
from anno_save_analyzer.tui.state import TuiState


def _make_balance() -> SupplyBalanceTable:
    return SupplyBalanceTable(
        islands=(
            IslandBalance(
                area_manager="AreaManager_1",
                city_name="大都会岡山",
                resident_total=1000,
                products=(
                    ProductBalance(
                        product_guid=1010200, produced_per_minute=4.0, consumed_per_minute=2.0
                    ),
                    ProductBalance(
                        product_guid=1010257, produced_per_minute=1.0, consumed_per_minute=3.0
                    ),
                ),
            ),
            IslandBalance(
                area_manager="AreaManager_2",
                city_name="広島支社",
                resident_total=500,
                products=(
                    ProductBalance(
                        product_guid=1010200, produced_per_minute=1.0, consumed_per_minute=1.5
                    ),
                ),
            ),
        )
    )


@pytest.fixture
def tui_state_with_balance(tui_state) -> TuiState:
    """Anno 1800 扱いで balance_table を注入した state を返す．"""
    return dataclasses.replace(
        tui_state,
        title=GameTitle.ANNO_1800,
        balance_table=_make_balance(),
    )


class TestSupplyBalanceInstall:
    async def test_screen_installed_when_balance_present(self, tui_state_with_balance) -> None:
        app = TradeApp(tui_state_with_balance)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert "supply_balance" in pilot.app._installed_screens

    async def test_screen_not_installed_when_balance_none(self, tui_state) -> None:
        """既存 fixture は balance_table=None．install されないことを確認．"""
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert "supply_balance" not in pilot.app._installed_screens


class TestSupplyBalanceScreenFlow:
    async def test_ctrl_t_cycles_through_three_screens(self, tui_state_with_balance) -> None:
        """overview → statistics → supply_balance → overview の循環．"""
        from anno_save_analyzer.tui.screens import OverviewScreen, TradeStatisticsScreen

        app = TradeApp(tui_state_with_balance)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(pilot.app.screen, OverviewScreen)
            await pilot.press("ctrl+t")
            await pilot.pause()
            assert isinstance(pilot.app.screen, TradeStatisticsScreen)
            await pilot.press("ctrl+t")
            await pilot.pause()
            assert isinstance(pilot.app.screen, SupplyBalanceScreen)
            await pilot.press("ctrl+t")
            await pilot.pause()
            assert isinstance(pilot.app.screen, OverviewScreen)

    async def test_datatable_populated_on_mount(self, tui_state_with_balance) -> None:
        app = TradeApp(tui_state_with_balance)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t", "ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, SupplyBalanceScreen)
            from textual.widgets import DataTable

            table = screen.query_one(DataTable)
            # 2 島とも select 済み初期状態で Fish (1010200, delta+1.5+-0.5=+1.5)
            # と Rum (1010257, delta-2) の 2 行
            assert table.row_count == 2

    async def test_deficit_only_filters(self, tui_state_with_balance) -> None:
        app = TradeApp(tui_state_with_balance)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t", "ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, SupplyBalanceScreen)
            from textual.widgets import DataTable

            table = screen.query_one(DataTable)
            # 'd' で deficit only → Rum だけ残る
            await pilot.press("d")
            await pilot.pause()
            assert table.row_count == 1

    async def test_select_none_clears_table_and_shows_summary_placeholder(
        self, tui_state_with_balance
    ) -> None:
        app = TradeApp(tui_state_with_balance)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t", "ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            from textual.widgets import DataTable, Static

            await pilot.press("n")
            await pilot.pause()
            table = screen.query_one(DataTable)
            # 何も選択されてないときは空行
            assert table.row_count == 0
            summary = screen.query_one("#balance-summary", Static)
            # プレースホルダ文言がセットされている (具体的な文字列は locale による)
            assert str(summary.render())


def test_save_path_is_real_path(tui_state_with_balance) -> None:
    """念のため state fixture の save_path が Path で素直に使えること．"""
    assert isinstance(tui_state_with_balance.save_path, Path)
    assert tui_state_with_balance.balance_table is not None
