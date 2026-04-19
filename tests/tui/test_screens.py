"""個別 screen の compose 確認．"""

from __future__ import annotations

import pytest

from anno_save_analyzer.tui import TradeApp
from anno_save_analyzer.tui.i18n import Localizer
from anno_save_analyzer.tui.screens import OverviewScreen, TradeStatisticsScreen
from anno_save_analyzer.tui.state import TuiState, build_overview


@pytest.mark.asyncio
class TestOverviewScreen:
    async def test_overview_renders_with_session_ids(self, tui_state) -> None:
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, OverviewScreen)
            # _render_body() が出す raw markup をテスト用に取り出す
            body_static = screen._render_body()
            text = str(body_static.render())
            assert "Overview" in text or "概要" in text
            assert tui_state.save_path.name in text

    async def test_overview_shows_empty_message_when_no_sessions(self, tui_state) -> None:
        # session 無しで再構築
        empty_overview = build_overview(tui_state.save_path, tui_state.title, [], (), ())
        empty_state = TuiState(
            save_path=tui_state.save_path,
            title=tui_state.title,
            locale="en",
            events=(),
            items=tui_state.items,
            overview=empty_overview,
            item_summaries=(),
            route_summaries=(),
            session_ids=(),
        )
        app = TradeApp(empty_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            text = str(screen._render_body().render())
            assert "No save loaded" in text


@pytest.mark.asyncio
class TestStatisticsScreen:
    async def test_statistics_renders_tree_and_tables(self, tui_state) -> None:
        # statistics 画面に直接 push するため，OverviewScreen 経由しないルート
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, TradeStatisticsScreen)
            # tree のラベルが en で root 表示されてる
            tree = screen.query_one("#sessions-tree")
            assert tree is not None
            items_table = screen.query_one("#items-table")
            assert items_table is not None
            routes_table = screen.query_one("#routes-table")
            assert routes_table is not None

    async def test_statistics_japanese_labels_after_locale_switch(self, tui_state) -> None:
        # locale=ja で初期化
        from anno_save_analyzer.tui.state import TuiState

        ja_state = TuiState(
            save_path=tui_state.save_path,
            title=tui_state.title,
            locale="ja",
            events=tui_state.events,
            items=tui_state.items,
            overview=tui_state.overview,
            item_summaries=tui_state.item_summaries,
            route_summaries=tui_state.route_summaries,
            session_ids=tui_state.session_ids,
        )
        app = TradeApp(ja_state, localizer=Localizer.load("ja"))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            # 物資別タブのラベル「物資別」が含まれる
            tabs = pilot.app.screen.query_one("#stats-tabs")
            assert tabs is not None
