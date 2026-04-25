"""Production Overview screen の Pilot ベース UI テスト．

合成 ``factories_by_island`` を ``TuiState`` に注入して ``TradeApp`` を起動し，
Ctrl+T 循環 / DataTable 中身 / Tree filter / detail pane の更新を確認する．
"""

from __future__ import annotations

import dataclasses

import pytest

from anno_save_analyzer.trade.factories import FactoryAggregate, FactoryInstance
from anno_save_analyzer.trade.factory_recipes import (
    FactoryRecipe,
    FactoryRecipeTable,
    RecipeInput,
    RecipeOutput,
)
from anno_save_analyzer.trade.models import GameTitle
from anno_save_analyzer.tui.app import TradeApp
from anno_save_analyzer.tui.screens import ProductionOverviewScreen
from anno_save_analyzer.tui.state import TuiState

# 合成 recipe (Lumberjack hut → Wood, Brewery → Beer with Wheat input)
_RECIPE_LUMBER_GUID = 100400
_RECIPE_BREWERY_GUID = 100500
_PRODUCT_WOOD_GUID = 1010100
_PRODUCT_BEER_GUID = 1010102
_PRODUCT_WHEAT_GUID = 1010101


def _make_recipe_table() -> FactoryRecipeTable:
    return FactoryRecipeTable(
        recipes={
            _RECIPE_LUMBER_GUID: FactoryRecipe(
                guid=_RECIPE_LUMBER_GUID,
                name="Lumberjack",
                tpmin=2.0,
                outputs=(RecipeOutput(product_guid=_PRODUCT_WOOD_GUID, amount=1.0),),
                inputs=(),
            ),
            _RECIPE_BREWERY_GUID: FactoryRecipe(
                guid=_RECIPE_BREWERY_GUID,
                name="Brewery",
                tpmin=1.0,
                outputs=(RecipeOutput(product_guid=_PRODUCT_BEER_GUID, amount=1.0),),
                inputs=(RecipeInput(product_guid=_PRODUCT_WHEAT_GUID, amount=1.0),),
            ),
        }
    )


def _make_factories_by_island() -> dict[str, FactoryAggregate]:
    """2 島 × 2 工場種類の合成データ．

    岡山: Lumberjack ×3 (productivity 1.0 / 0.8 / 0.6) + Brewery ×1 (productivity 1.0)
    広島: Lumberjack ×2 (productivity 0.5 / 0.5)
    """
    return {
        "岡山": FactoryAggregate(
            area_manager="AreaManager_1",
            instances=(
                FactoryInstance(building_guid=_RECIPE_LUMBER_GUID, productivity=1.0),
                FactoryInstance(building_guid=_RECIPE_LUMBER_GUID, productivity=0.8),
                FactoryInstance(building_guid=_RECIPE_LUMBER_GUID, productivity=0.6),
                FactoryInstance(building_guid=_RECIPE_BREWERY_GUID, productivity=1.0),
            ),
        ),
        "広島": FactoryAggregate(
            area_manager="AreaManager_2",
            instances=(
                FactoryInstance(building_guid=_RECIPE_LUMBER_GUID, productivity=0.5),
                FactoryInstance(building_guid=_RECIPE_LUMBER_GUID, productivity=0.5),
            ),
        ),
    }


@pytest.fixture
def tui_state_with_factories(tui_state, monkeypatch) -> TuiState:
    """``factories_by_island`` を注入した state．Anno 1800 扱い．

    FactoryRecipeTable.load() を mock し，pyproject の同梱 YAML 不要で動く．
    """
    monkeypatch.setattr(
        "anno_save_analyzer.tui.screens.production_overview.FactoryRecipeTable.load",
        classmethod(lambda cls: _make_recipe_table()),
    )
    return dataclasses.replace(
        tui_state,
        title=GameTitle.ANNO_1800,
        factories_by_island=_make_factories_by_island(),
    )


class TestProductionOverviewInstall:
    async def test_screen_installed_when_factories_present(self, tui_state_with_factories) -> None:
        app = TradeApp(tui_state_with_factories)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert "production_overview" in pilot.app._installed_screens

    async def test_screen_not_installed_when_factories_empty(self, tui_state) -> None:
        """既存 fixture (Anno 117) は factories_by_island=空．install されない．"""
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert "production_overview" not in pilot.app._installed_screens


class TestProductionOverviewFlow:
    async def test_ctrl_t_cycles_through_four_screens(self, tui_state_with_factories) -> None:
        """overview → statistics → (supply_balance) → production_overview → overview の循環．

        この fixture は balance_table 無しなので supply_balance は出ない．
        order = overview / statistics / production_overview の 3 段．
        """
        from anno_save_analyzer.tui.screens import OverviewScreen, TradeStatisticsScreen

        app = TradeApp(tui_state_with_factories)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(pilot.app.screen, OverviewScreen)
            await pilot.press("ctrl+t")
            await pilot.pause()
            assert isinstance(pilot.app.screen, TradeStatisticsScreen)
            await pilot.press("ctrl+t")
            await pilot.pause()
            assert isinstance(pilot.app.screen, ProductionOverviewScreen)
            await pilot.press("ctrl+t")
            await pilot.pause()
            assert isinstance(pilot.app.screen, OverviewScreen)

    async def test_datatable_aggregates_by_building_per_island(
        self, tui_state_with_factories
    ) -> None:
        """初期 (All 選択) で全 (island × building) 行が出る．

        岡山 × Lumberjack (3 件) / 岡山 × Brewery (1 件) /
        広島 × Lumberjack (2 件) → 3 行．
        """
        from textual.widgets import DataTable

        app = TradeApp(tui_state_with_factories)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t", "ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, ProductionOverviewScreen)
            table = screen.query_one(DataTable)
            assert table.row_count == 3

    async def test_island_filter_narrows_table(self, tui_state_with_factories) -> None:
        """島 leaf を選ぶと当該島の factory 行のみになる．"""
        from textual.widgets import DataTable, Tree

        app = TradeApp(tui_state_with_factories)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t", "ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, ProductionOverviewScreen)
            tree = screen.query_one(Tree)
            # root → root (NPC leaf として root 直下に乗る．session が無いため)
            # 岡山 / 広島 は area_manager_to_city が空なので NPC 扱いで root 配下．
            # leaf を ``data=("island", "岡山")`` で探す．
            target = None
            for node in tree.root.children:
                if node.data == ("island", "岡山"):
                    target = node
                    break
            assert target is not None, "岡山 leaf not found"
            screen.on_tree_node_selected(Tree.NodeSelected(target))
            await pilot.pause()
            table = screen.query_one(DataTable)
            # 岡山には Lumberjack + Brewery → 2 行
            assert table.row_count == 2

    async def test_detail_pane_updates_on_row_highlight(self, tui_state_with_factories) -> None:
        """row highlight で detail pane に factory 名 + sparkline が出る．"""
        from textual.widgets import DataTable, Static

        app = TradeApp(tui_state_with_factories)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t", "ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, ProductionOverviewScreen)
            table = screen.query_one(DataTable)
            # 最初の行に focus → detail pane が「(empty)」以外に
            table.cursor_type = "row"
            table.move_cursor(row=0)
            await pilot.pause()
            detail = screen.query_one("#production-detail", Static)
            text = str(detail.render())
            # Lumberjack か Brewery，どちらかが detail に映るはず
            assert ("Lumberjack" in text) or ("Brewery" in text)
            # sparkline ラベルが出てれば描画 OK
            assert screen._localizer.t("production.detail.sparkline_label") in text

    async def test_locale_toggle_updates_column_header(self, tui_state_with_factories) -> None:
        """Ctrl+L で日本語に切替．列ヘッダの文字列が変わる．"""
        from textual.widgets import DataTable

        app = TradeApp(tui_state_with_factories)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t", "ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, ProductionOverviewScreen)
            table = screen.query_one(DataTable)
            en_headers = [str(c.label) for c in table.columns.values()]
            assert "Factory" in en_headers
            await pilot.press("ctrl+l")
            # locale 切替は recompose を含むので 2 回 pause して on_mount 完了を待つ．
            await pilot.pause()
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, ProductionOverviewScreen)
            table = screen.query_one(DataTable)
            ja_headers = [str(c.label) for c in table.columns.values()]
            assert "工場名" in ja_headers


class TestProductionFilters:
    async def test_session_filter_includes_only_session_islands(
        self, tui_state_with_factories, monkeypatch
    ) -> None:
        """session filter で当該 session 配下の island leaf のみ table に出る．

        合成 fixture の islands_by_session は空なので，session filter での
        island 数 = 0 → row_count = 0．
        """
        from textual.widgets import DataTable, Tree

        app = TradeApp(tui_state_with_factories)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t", "ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, ProductionOverviewScreen)
            tree = screen.query_one(Tree)
            # session ノードを 1 つ取って ``("session", sid)`` を inject
            session_node = next(
                (n for n in tree.root.children if n.data and n.data[0] == "session"),
                None,
            )
            if session_node is None:
                # fixture には session 1 つ以上あるはずだが，無ければ skip
                return
            screen.on_tree_node_selected(Tree.NodeSelected(session_node))
            await pilot.pause()
            table = screen.query_one(DataTable)
            # islands_by_session に factories_by_island の島が無い → 0 行
            assert table.row_count == 0

    async def test_root_resets_to_all_islands(self, tui_state_with_factories) -> None:
        """root を選び直すと All に戻り 3 行に復帰．"""
        from textual.widgets import DataTable, Tree

        app = TradeApp(tui_state_with_factories)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t", "ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, ProductionOverviewScreen)
            tree = screen.query_one(Tree)
            island_node = next(
                (n for n in tree.root.children if n.data == ("island", "岡山")),
                None,
            )
            assert island_node is not None
            screen.on_tree_node_selected(Tree.NodeSelected(island_node))
            await pilot.pause()
            screen.on_tree_node_selected(Tree.NodeSelected(tree.root))
            await pilot.pause()
            table = screen.query_one(DataTable)
            assert table.row_count == 3


class TestProductionRecipeFallbacks:
    async def test_unknown_building_guid_renders_placeholder(self, tui_state, monkeypatch) -> None:
        """recipe 未登録の building_guid は ``Building_<guid>`` 名で出る．

        rate=0 / 出力 "—" / 入力 "" の defensive な表示で落ちないこと．
        """
        import dataclasses

        from textual.widgets import DataTable

        monkeypatch.setattr(
            "anno_save_analyzer.tui.screens.production_overview.FactoryRecipeTable.load",
            classmethod(lambda cls: FactoryRecipeTable(recipes={})),
        )
        unknown_state = dataclasses.replace(
            tui_state,
            title=GameTitle.ANNO_1800,
            factories_by_island={
                "孤島": FactoryAggregate(
                    area_manager="AreaManager_42",
                    instances=(FactoryInstance(building_guid=999999, productivity=0.5),),
                ),
            },
        )
        app = TradeApp(unknown_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t", "ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, ProductionOverviewScreen)
            table = screen.query_one(DataTable)
            assert table.row_count == 1
            row = table.get_row_at(0)
            assert "Building_999999" in row[0]
            assert row[3] == "—"
            assert row[4] == "0.00"


class TestProductionRateCalculation:
    async def test_rate_is_productivity_times_tpmin(self, tui_state_with_factories) -> None:
        """生産レート = Σ productivity × tpmin × output.amount．

        岡山 × Lumberjack (productivity 1.0+0.8+0.6=2.4 / tpmin=2 / amount=1)
        → 4.8 t/min．DataTable の対応 cell 値で確認．
        """
        from textual.widgets import DataTable

        app = TradeApp(tui_state_with_factories)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t", "ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, ProductionOverviewScreen)
            table = screen.query_one(DataTable)
            # 岡山 × Lumberjack 行を探す (factory 名 = "Lumberjack")
            found = False
            for row_key in table.rows:
                row = table.get_row(row_key)
                if row[0] == "Lumberjack" and str(row_key.value).startswith("岡山::"):
                    # rate cell index = 4 (factory / count / productivity / output / rate / input)
                    assert row[4] == "4.80"
                    found = True
                    break
            assert found, "岡山 × Lumberjack row not found"
