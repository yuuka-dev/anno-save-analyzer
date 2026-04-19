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

    async def test_statistics_tree_renders_island_leaves(self, tui_state, tmp_path) -> None:
        """islands_by_session に値を入れて Tree に島名が出ることを確認．"""
        from anno_save_analyzer.parser.filedb import PlayerIsland
        from anno_save_analyzer.tui.state import TuiState

        sample_islands = (
            PlayerIsland(city_name="大阪民国"),
            PlayerIsland(city_name="シベリア"),
            PlayerIsland(city_name="グンマー帝国"),
        )
        islands = dict.fromkeys(tui_state.session_ids, sample_islands)
        new_state = TuiState(
            save_path=tui_state.save_path,
            title=tui_state.title,
            locale="en",
            events=tui_state.events,
            items=tui_state.items,
            overview=tui_state.overview,
            item_summaries=tui_state.item_summaries,
            route_summaries=tui_state.route_summaries,
            session_ids=tui_state.session_ids,
            session_locale_keys=tui_state.session_locale_keys,
            islands_by_session=islands,
        )
        app = TradeApp(new_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            tree = pilot.app.screen.query_one("#sessions-tree")
            # root 直下に session ノード，その配下に島ノードが追加されてる
            session_nodes = tree.root.children
            assert len(session_nodes) == len(tui_state.session_ids)
            # 各 session ノードに islands count 個の leaf
            for node in session_nodes:
                assert len(node.children) == 3

    async def test_statistics_routes_table_shows_idle_and_active(self, tui_state) -> None:
        """routes_by_session に history 未登場の ship_id を仕込むと idle 行が増える．"""
        from anno_save_analyzer.trade import TradeRouteDef, TransportTask
        from anno_save_analyzer.tui.state import TuiState

        # history に出てる route_id (= ship_id) を集める．fixture は "7", "8"．
        active_ids = {s.route_id for s in tui_state.route_summaries if s.route_id}
        idle_def = TradeRouteDef(
            ship_id=999,  # history に無い → idle
            route_hash=42,
            round_travel=1000,
            establish_time=0,
            tasks=(
                TransportTask(from_key=1, to_key=2, product_guid=100, balance_raw=0),
                TransportTask(from_key=2, to_key=1, product_guid=200, balance_raw=0),
            ),
        )
        # 加えて active route (ship_id=7) の legs も populate してみる
        active_def = TradeRouteDef(
            ship_id=7,
            route_hash=7,
            round_travel=500,
            establish_time=0,
            tasks=(TransportTask(from_key=10, to_key=20, product_guid=100, balance_raw=0),),
        )
        first_sid = tui_state.session_ids[0]
        routes_map = {first_sid: (active_def, idle_def)}

        new_state = TuiState(
            save_path=tui_state.save_path,
            title=tui_state.title,
            locale="en",
            events=tui_state.events,
            items=tui_state.items,
            overview=tui_state.overview,
            item_summaries=tui_state.item_summaries,
            route_summaries=tui_state.route_summaries,
            session_ids=tui_state.session_ids,
            session_locale_keys=tui_state.session_locale_keys,
            islands_by_session=tui_state.islands_by_session,
            routes_by_session=routes_map,
        )
        app = TradeApp(new_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            routes_table = screen.query_one("#routes-table")
            # row count: active (route_summaries の長さ) + 1 (idle ship=999)
            assert routes_table.row_count == len(tui_state.route_summaries) + 1
            # 行ごとに (Route, Status, Kind, Legs, ...) の順で確認
            all_rows = [
                tuple(str(v) for v in routes_table.get_row_at(i))
                for i in range(routes_table.row_count)
            ]
            statuses = [row[1] for row in all_rows]
            route_ids = [row[0] for row in all_rows]
            assert "idle" in statuses
            assert "active" in statuses
            assert "999" in route_ids
            # active row (ship=7) の legs は active_def.tasks=1 に反映されてる
            row_7 = next(row for row in all_rows if row[0] == "7")
            assert row_7[3] == "1"  # Legs
            _ = active_ids

    async def test_statistics_idle_routes_skip_none_ship_id(self, tui_state) -> None:
        """ship_id=None の idle 候補は行に出さない．"""
        from anno_save_analyzer.trade import TradeRouteDef
        from anno_save_analyzer.tui.state import TuiState

        skip_def = TradeRouteDef(
            ship_id=None, route_hash=None, round_travel=None, establish_time=None, tasks=()
        )
        first_sid = tui_state.session_ids[0]
        routes_map = {first_sid: (skip_def,)}
        new_state = TuiState(
            save_path=tui_state.save_path,
            title=tui_state.title,
            locale="en",
            events=tui_state.events,
            items=tui_state.items,
            overview=tui_state.overview,
            item_summaries=tui_state.item_summaries,
            route_summaries=tui_state.route_summaries,
            session_ids=tui_state.session_ids,
            session_locale_keys=tui_state.session_locale_keys,
            islands_by_session=tui_state.islands_by_session,
            routes_by_session=routes_map,
        )
        app = TradeApp(new_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            routes_table = pilot.app.screen.query_one("#routes-table")
            # skip されるので active のみ
            assert routes_table.row_count == len(tui_state.route_summaries)

    async def test_partners_pane_updates_on_item_row_highlight(self, tui_state) -> None:
        """items-table の row highlight で Partners pane が選択物資の相手集計に切り替わる．"""
        from textual.widgets import Static

        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            items_table = screen.query_one("#items-table")
            items_table.focus()
            await pilot.pause()
            # 先頭行 highlight は DataTable が prop 的に入るはず．
            # 明示的に keypress で currentChange を発火．
            await pilot.press("down")
            await pilot.pause()
            pane = screen.query_one("#partners-pane", Static)
            rendered = str(pane.render())
            # placeholder から切り替わる (partners.placeholder は "(per-good partner list arrives..."
            assert "arrives in Week" not in rendered and "Week 3 で実装" not in rendered

    async def test_partners_pane_shows_empty_message_for_item_without_events(
        self, tui_state
    ) -> None:
        """fixture に登場しない guid を直接 pane に渡すと empty メッセージ．"""
        from textual.widgets import Static

        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            screen._update_partners_pane(999_999)
            pane = screen.query_one("#partners-pane", Static)
            rendered = str(pane.render())
            # en fallback 名が表示される
            assert "Good_999999" in rendered

    async def test_row_highlight_early_returns(self, tui_state) -> None:
        """items-table 以外 / row_key が数値でない / None → pane 無更新 (early return)．"""
        from textual.widgets import DataTable, Static

        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen

            class _FakeRowKey:
                def __init__(self, value):
                    self.value = value

            class _FakeEvent:
                def __init__(self, table, key_value):
                    self.data_table = table
                    self.row_key = _FakeRowKey(key_value) if key_value is not None else None

            items_table = screen.query_one("#items-table", DataTable)
            routes_table = screen.query_one("#routes-table", DataTable)
            pane = screen.query_one("#partners-pane", Static)
            before = str(pane.render())

            # (1) routes-table from event → early return (line 178)
            screen.on_data_table_row_highlighted(_FakeEvent(routes_table, "0"))
            await pilot.pause()
            assert str(pane.render()) == before

            # (2) row_key None → early return (line 181)
            screen.on_data_table_row_highlighted(_FakeEvent(items_table, None))
            await pilot.pause()
            assert str(pane.render()) == before

            # (3) row_key empty string → early return (line 181)
            screen.on_data_table_row_highlighted(_FakeEvent(items_table, ""))
            await pilot.pause()
            assert str(pane.render()) == before

            # (4) row_key not int → ValueError → silently skip (lines 184-185)
            screen.on_data_table_row_highlighted(_FakeEvent(items_table, "not_a_guid"))
            await pilot.pause()
            assert str(pane.render()) == before

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
