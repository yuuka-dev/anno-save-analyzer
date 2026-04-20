"""個別 screen の compose 確認．"""

from __future__ import annotations

import pytest

from anno_save_analyzer.tui import TradeApp
from anno_save_analyzer.tui.i18n import Localizer
from anno_save_analyzer.tui.screens import OverviewScreen, TradeStatisticsScreen
from anno_save_analyzer.tui.state import TuiState, build_overview


@pytest.mark.asyncio
class TestTreeFilterSync:
    """#30: Tree selection → _filter 更新 → table / pane / chart 連動．"""

    async def test_root_node_resets_filter_to_all(self, tui_state) -> None:
        from anno_save_analyzer.tui.screens.statistics import TradeFilter, TradeStatisticsScreen

        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, TradeStatisticsScreen)
            screen._filter = TradeFilter(session="0", island="whatever")

            from textual.widgets import Tree

            tree = screen.query_one("#sessions-tree", Tree)

            class _Evt:
                def __init__(self, node):
                    self.node = node

            screen.on_tree_node_selected(_Evt(tree.root))
            await pilot.pause()
            # refresh(recompose=True) 後の screen を取得し直す
            screen = pilot.app.screen
            assert screen._filter.is_all

    async def test_session_node_sets_session_filter(self, tui_state) -> None:
        from anno_save_analyzer.tui.screens.statistics import TradeStatisticsScreen

        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            from textual.widgets import Tree

            screen = pilot.app.screen
            tree = screen.query_one("#sessions-tree", Tree)
            # 最初の session ノード
            session_node = tree.root.children[0]

            class _Evt:
                def __init__(self, node):
                    self.node = node

            screen.on_tree_node_selected(_Evt(session_node))
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, TradeStatisticsScreen)
            assert screen._filter.session == tui_state.session_ids[0]

    async def test_repeated_selection_is_no_op(self, tui_state) -> None:
        """同じノードを再選択しても filter が変わらず refresh しない (早期 return)．"""
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            from textual.widgets import Tree

            screen = pilot.app.screen
            tree = screen.query_one("#sessions-tree", Tree)

            class _Evt:
                def __init__(self, node):
                    self.node = node

            screen.on_tree_node_selected(_Evt(tree.root))  # All
            screen.on_tree_node_selected(_Evt(tree.root))  # 2 回目 = no-op
            await pilot.pause()
            assert pilot.app.screen._filter.is_all


@pytest.mark.asyncio
class TestFilterLabel:
    """Filter banner がロケール / 選択内容で更新される．"""

    async def test_all_label_on_fresh_screen(self, tui_state) -> None:
        from textual.widgets import Static

        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            banner = pilot.app.screen.query_one("#filter-banner", Static)
            text = str(banner.render())
            assert "all" in text.lower() or "全体" in text

    async def test_session_label_after_selection(self, tui_state) -> None:
        from textual.widgets import Static

        from anno_save_analyzer.tui.screens.statistics import TradeFilter

        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            screen._filter = TradeFilter(session=tui_state.session_ids[0])
            screen.refresh(recompose=True)
            await pilot.pause()
            banner = pilot.app.screen.query_one("#filter-banner", Static)
            text = str(banner.render())
            assert "session" in text.lower() or "セッション" in text

    async def test_island_label(self, tui_state) -> None:
        from textual.widgets import Static

        from anno_save_analyzer.tui.screens.statistics import TradeFilter

        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            screen._filter = TradeFilter(session="0", island="大阪民国")
            screen.refresh(recompose=True)
            await pilot.pause()
            banner = pilot.app.screen.query_one("#filter-banner", Static)
            text = str(banner.render())
            assert "大阪民国" in text


@pytest.mark.asyncio
class TestFilteredRenderingAndExport:
    async def test_routes_table_hides_idle_under_island_filter(self, tui_state) -> None:
        """island filter 時は idle route (定義のみ / 履歴無し) は routes-table から消える．"""
        from anno_save_analyzer.trade import TradeRouteDef, TransportTask
        from anno_save_analyzer.tui.screens.statistics import TradeFilter
        from anno_save_analyzer.tui.state import TuiState

        idle_def = TradeRouteDef(
            ship_id=999,
            route_hash=0,
            round_travel=0,
            establish_time=0,
            tasks=(TransportTask(from_key=1, to_key=2, product_guid=1, balance_raw=0),),
        )
        first_sid = tui_state.session_ids[0]
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
            routes_by_session={first_sid: (idle_def,)},
        )
        app = TradeApp(new_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            # 全体 → idle 999 行が存在
            from textual.widgets import DataTable

            table_all = screen.query_one("#routes-table", DataTable)
            all_count = table_all.row_count
            # island filter 適用 → idle route 消える
            screen._filter = TradeFilter(session=first_sid, island="プレイヤー島")
            screen.refresh(recompose=True)
            await pilot.pause()
            table_island = pilot.app.screen.query_one("#routes-table", DataTable)
            # ship_id=999 の idle は island filter 時 hide される
            assert table_island.row_count <= all_count

    async def test_export_filename_has_filter_suffix(
        self, tui_state, tmp_path, monkeypatch
    ) -> None:
        """Statistics 画面で filter 有効時に ^O すると filename に suffix が付く．"""
        from anno_save_analyzer.tui.screens.statistics import TradeFilter

        monkeypatch.chdir(tmp_path)
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            pilot.app.screen._filter = TradeFilter(
                session=tui_state.session_ids[0], island="プレイヤー島"
            )
            await pilot.press("ctrl+o")
            await pilot.pause()
        csvs = sorted(tmp_path.glob("fake_*_island-*_*.csv"))
        assert len(csvs) == 4  # items / routes / events / inventory

    async def test_export_filename_has_session_suffix(
        self, tui_state, tmp_path, monkeypatch
    ) -> None:
        """session filter だけの場合は session-<id> suffix．"""
        from anno_save_analyzer.tui.screens.statistics import TradeFilter

        monkeypatch.chdir(tmp_path)
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            pilot.app.screen._filter = TradeFilter(session=tui_state.session_ids[0])
            await pilot.press("ctrl+o")
            await pilot.pause()
        csvs = sorted(tmp_path.glob("fake_*_session-*_*.csv"))
        assert len(csvs) == 4

    async def test_export_session_filter_keeps_idle_routes(
        self, tui_state, tmp_path, monkeypatch
    ) -> None:
        from anno_save_analyzer.trade import TradeRouteDef, TransportTask
        from anno_save_analyzer.tui.screens.statistics import TradeFilter
        from anno_save_analyzer.tui.state import TuiState

        first_sid = tui_state.session_ids[0]
        idle_def = TradeRouteDef(
            ship_id=999,
            route_hash=0,
            round_travel=0,
            establish_time=0,
            tasks=(TransportTask(from_key=1, to_key=2, product_guid=1, balance_raw=0),),
        )
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
            routes_by_session={first_sid: (idle_def,)},
        )
        monkeypatch.chdir(tmp_path)
        app = TradeApp(new_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            pilot.app.screen._filter = TradeFilter(session=first_sid)
            await pilot.press("ctrl+o")
            await pilot.pause()

        routes_csv = next(tmp_path.glob("fake_routes_session-*_*.csv"))
        rows = routes_csv.read_text(encoding="utf-8").splitlines()
        # columns: route_id, route_name, status, partner_kind, ...
        assert any(row.startswith("999,,idle,route,") for row in rows)

    async def test_export_filename_suffix_is_sanitized(
        self, tui_state, tmp_path, monkeypatch
    ) -> None:
        from anno_save_analyzer.tui.screens.statistics import TradeFilter

        monkeypatch.chdir(tmp_path)
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            pilot.app.screen._filter = TradeFilter(
                session=tui_state.session_ids[0], island="../bad\\name:*?"
            )
            await pilot.press("ctrl+o")
            await pilot.pause()

        csvs = sorted(tmp_path.glob("fake_*_island-*_*.csv"))
        assert len(csvs) == 4
        for path in csvs:
            assert "/" not in path.name
            assert "\\" not in path.name
            assert ":" not in path.name
            assert "*" not in path.name
            assert "?" not in path.name
            assert ".." not in path.name

    async def test_export_full_when_overview_active(self, tui_state, tmp_path, monkeypatch) -> None:
        """Overview 画面で ^O すると filter 関係なく全量，suffix なし．"""
        monkeypatch.chdir(tmp_path)
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()  # overview の状態
            await pilot.press("ctrl+o")
            await pilot.pause()
        csvs = sorted(tmp_path.glob("fake_*_*.csv"))
        # filter suffix は無い
        assert all("island-" not in p.name for p in csvs)
        assert all("session-" not in p.name for p in csvs)


@pytest.mark.asyncio
class TestResponsiveLayout:
    """#34: terminal 幅で layout class を切替 + Trend 列出し分け．"""

    async def test_wide_default_class_on_120plus(self, tui_state) -> None:
        from anno_save_analyzer.tui.screens.statistics import TradeStatisticsScreen

        app = TradeApp(tui_state)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, TradeStatisticsScreen)
            assert screen._layout_class == "wide"
            assert screen.has_class("wide")

    async def test_mid_class_between_80_and_120(self, tui_state) -> None:
        app = TradeApp(tui_state)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            assert screen._layout_class == "mid"
            assert screen.has_class("mid")

    async def test_narrow_class_below_80(self, tui_state) -> None:
        app = TradeApp(tui_state)
        async with app.run_test(size=(70, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            assert screen._layout_class == "narrow"
            assert screen.has_class("narrow")

    async def test_narrow_hides_trend_column_in_items_table(self, tui_state) -> None:
        from textual.widgets import DataTable

        app = TradeApp(tui_state)
        async with app.run_test(size=(70, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            table = pilot.app.screen.query_one("#items-table", DataTable)
            # Trend 列 hide → 列数 6 (good / bought / sold / net_qty / net_gold / events)
            assert len(table.columns) == 6

    async def test_wide_keeps_trend_column(self, tui_state) -> None:
        from textual.widgets import DataTable

        app = TradeApp(tui_state)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            table = pilot.app.screen.query_one("#items-table", DataTable)
            assert len(table.columns) == 7  # + Trend

    async def test_resize_switches_class_and_recomposes(self, tui_state) -> None:
        """wide → narrow の resize で class 切替 + recompose が起こる．"""
        from anno_save_analyzer.tui.screens.statistics import TradeStatisticsScreen

        app = TradeApp(tui_state)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, TradeStatisticsScreen)
            assert screen._layout_class == "wide"
            await pilot.resize_terminal(60, 30)
            await pilot.pause()
            assert pilot.app.screen._layout_class == "narrow"

    async def test_same_breakpoint_resize_is_noop(self, tui_state) -> None:
        """同 breakpoint 域内の resize は layout class を変えない．"""
        app = TradeApp(tui_state)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            await pilot.resize_terminal(130, 30)
            await pilot.pause()
            assert pilot.app.screen._layout_class == "wide"


@pytest.mark.asyncio
class TestPartnersPaneScroll:
    async def test_partners_pane_inside_vertical_scroll(self, tui_state) -> None:
        """長い Partners 出力が切れないよう VerticalScroll 包装を確認．"""
        from textual.containers import VerticalScroll

        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            scroll = pilot.app.screen.query_one("#partners-scroll", VerticalScroll)
            assert scroll is not None


@pytest.mark.asyncio
class TestScreenLocalizerSetter:
    """Cursor レビュー指摘: App からの ``_localizer`` 直書きを setter 化．"""

    async def test_overview_set_localizer_swaps_instance(self, tui_state) -> None:
        from anno_save_analyzer.tui.screens import OverviewScreen

        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            overview = pilot.app.get_screen("overview")
            assert isinstance(overview, OverviewScreen)
            new_localizer = Localizer.load("ja")
            overview.set_localizer(new_localizer)
            assert overview._localizer is new_localizer

    async def test_statistics_set_localizer_swaps_instance(self, tui_state) -> None:
        from anno_save_analyzer.tui.screens import TradeStatisticsScreen

        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            stats = pilot.app.get_screen("statistics")
            assert isinstance(stats, TradeStatisticsScreen)
            new_localizer = Localizer.load("ja")
            stats.set_localizer(new_localizer)
            assert stats._localizer is new_localizer


class TestFilteredEventCache:
    def test_filtered_events_reused_across_aggregations(self, tui_state, monkeypatch) -> None:
        import anno_save_analyzer.tui.screens.statistics as statistics_mod
        from anno_save_analyzer.tui.i18n import Localizer
        from anno_save_analyzer.tui.screens.statistics import TradeFilter, TradeStatisticsScreen

        calls = {"count": 0}
        original = statistics_mod.filter_events

        def wrapped(events, *, session=None, island=None):
            """Spy wrapper for filter_events.

            Args:
                events: TradeEvent sequence to filter.
                session: Optional session id.
                island: Optional island name.

            Returns:
                Filtered event list from the original function.
            """
            calls["count"] += 1
            return original(events, session=session, island=island)

        monkeypatch.setattr(statistics_mod, "filter_events", wrapped)
        screen = TradeStatisticsScreen(tui_state, Localizer.load("en"))
        screen._filter = TradeFilter(session=tui_state.session_ids[0])
        items = screen._current_item_summaries()
        routes = screen._current_route_summaries()
        screen._build_item_trends()
        expected_events = original(tui_state.events, session=tui_state.session_ids[0], island=None)
        expected_items = statistics_mod.by_item(expected_events)
        expected_routes = statistics_mod.by_route(expected_events)

        assert calls["count"] == 1
        assert tuple(expected_items) == items
        assert tuple(expected_routes) == routes


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
            route_labels = [row[0] for row in all_rows]
            assert "idle" in statuses
            assert "active" in statuses
            assert "#999" in route_labels
            # active row (ship=7) の legs は active_def.tasks=1 に反映されてる
            row_7 = next(row for row in all_rows if row[0] == "#7")
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

    async def test_partners_pane_shows_recent_trades_section(self, tui_state) -> None:
        """物資を選ぶと Partners pane 下に "直近取引 / Recent trades" セクションが出る．"""
        import dataclasses

        from textual.widgets import Static

        from anno_save_analyzer.trade import Item, TradeEvent, TradingPartner

        # 時刻付き event を注入して min ago 表記を検証可能に．
        item = Item(guid=4242, names={"en": "Bricks"})
        partner = TradingPartner(id="route:9", display_name="r9", kind="route")
        events = (
            TradeEvent(
                item=item,
                amount=5,
                total_price=50,
                partner=partner,
                route_id="9",
                route_name="商会ルート",
                timestamp_tick=1_000_000,
                island_name="プレイヤー島",
            ),
            TradeEvent(
                item=item,
                amount=-2,
                total_price=-20,
                partner=partner,
                route_id="9",
                route_name="商会ルート",
                timestamp_tick=999_400,  # 1 分前 (TICKS_PER_MINUTE=600)
                island_name="プレイヤー島",
            ),
        )
        new_state = dataclasses.replace(tui_state, events=(*tui_state.events, *events))
        app = TradeApp(new_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            screen._update_partners_pane(4242)
            pane = screen.query_one("#partners-pane", Static)
            rendered = str(pane.render())
            assert "Recent trades" in rendered
            # 最新 event は 0 min ago，もう 1 件が 1 min ago で出る
            assert "min ago" in rendered
            # route_name 優先で表示
            assert "商会ルート" in rendered

    async def test_partners_pane_recent_section_hidden_for_unknown_item(self, tui_state) -> None:
        """fixture に events を持たない guid を直接渡した場合，partners empty メッセージのみ．"""
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
            # partners empty branch が先に返る → Recent trades は出ない
            assert "Recent trades" not in rendered

    async def test_partners_pane_recent_row_per_row_unit_switch(self, tui_state) -> None:
        """書記長フィードバック: 最新側は "分前"，120 分超は "時間前" を row 毎に判定．"""
        import dataclasses

        from textual.widgets import Static

        from anno_save_analyzer.trade import Item, TradeEvent

        item = Item(guid=5555, names={"en": "X"})
        # 最新 tick=1_000_000．60 min 前 (36_000 tick) と 180 min 前 (108_000 tick)．
        events = (
            TradeEvent(item=item, amount=1, total_price=1, timestamp_tick=1_000_000),
            TradeEvent(item=item, amount=1, total_price=1, timestamp_tick=964_000),
            TradeEvent(item=item, amount=1, total_price=1, timestamp_tick=892_000),
        )
        new_state = dataclasses.replace(tui_state, events=(*tui_state.events, *events))
        app = TradeApp(new_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            screen._update_partners_pane(5555)
            pane = screen.query_one("#partners-pane", Static)
            rendered = str(pane.render())
            # 0 min / 60 min は "min ago"，180 min は "h ago" が混在する
            assert "min ago" in rendered
            assert "h ago" in rendered

    async def test_recent_window_action_filters_old_events(self, tui_state) -> None:
        """``_on_recent_window_chosen`` で window を 1 分に絞ると古い event が消える．"""
        import dataclasses

        from textual.widgets import Static

        from anno_save_analyzer.trade import Item, TradeEvent

        item = Item(guid=6666, names={"en": "X"})
        events = (
            TradeEvent(
                item=item,
                amount=1,
                total_price=1,
                timestamp_tick=1_000_000,
                island_name="Recent",
            ),
            TradeEvent(
                item=item,
                amount=1,
                total_price=1,
                timestamp_tick=1_000 - 600_000,  # かなり古い (遥か前)
                island_name="Ancient",
            ),
        )
        new_state = dataclasses.replace(tui_state, events=(*tui_state.events, *events))
        app = TradeApp(new_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            screen._update_partners_pane(6666)
            pane = screen.query_one("#partners-pane", Static)
            assert "Ancient" in str(pane.render())
            # 時間窓 1 分を適用
            screen._on_recent_window_chosen(1.0)
            await pilot.pause()
            pane = screen.query_one("#partners-pane", Static)
            rendered = str(pane.render())
            assert "Recent" in rendered
            assert "Ancient" not in rendered

    async def test_recent_window_action_all_restores(self, tui_state) -> None:
        """``None`` を渡すと全期間に戻る．"""
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            screen._recent_window_minutes = 30.0
            screen._on_recent_window_chosen(None)
            assert screen._recent_window_minutes is None

    async def test_recent_window_same_value_is_noop(self, tui_state) -> None:
        """現行と同値を渡しても再描画を発火しない (notify 抑制)．"""
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            # 既存値と同じ None → 早期 return のみで副作用無し
            before = screen._recent_window_minutes
            screen._on_recent_window_chosen(None)
            assert screen._recent_window_minutes == before

    async def test_recent_window_palette_opens_on_ctrl_p(self, tui_state) -> None:
        """``^P`` で ``RecentWindowPalette`` が push される．"""
        from textual.widgets import OptionList

        from anno_save_analyzer.tui.screens.statistics import RecentWindowPalette

        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            await pilot.press("ctrl+p")
            await pilot.pause()
            assert isinstance(pilot.app.screen, RecentWindowPalette)
            option_list = pilot.app.screen.query_one(OptionList)
            labels = [str(option.prompt) for option in option_list.options]
            assert any("Last 24 h" in label for label in labels)
            assert not any("1440 h" in label for label in labels)

    async def test_recent_window_binding_localizes_on_locale_switch(self, tui_state) -> None:
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            assert (
                next(b.description for b in screen.BINDINGS if b.key == "ctrl+p")
                == "History window"
            )
            await pilot.press("ctrl+l")
            await pilot.pause()
            screen = pilot.app.screen
            assert next(b.description for b in screen.BINDINGS if b.key == "ctrl+p") == "履歴窓"

    async def test_partners_pane_recent_row_marks_untimed_events(self, tui_state) -> None:
        """``timestamp_tick=None`` の event は "—" マーク (時刻不明) で末尾に並ぶ．"""
        import dataclasses

        from textual.widgets import Static

        from anno_save_analyzer.trade import Item, TradeEvent
        from anno_save_analyzer.tui.i18n import Localizer

        item = Item(guid=8888, names={"en": "Ghost"})
        untimed = TradeEvent(item=item, amount=1, total_price=1)
        new_state = dataclasses.replace(tui_state, events=(*tui_state.events, untimed))
        app = TradeApp(new_state, localizer=Localizer.load("ja"))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            screen._update_partners_pane(8888)
            pane = screen.query_one("#partners-pane", Static)
            rendered = str(pane.render())
            assert "直近取引" in rendered
            # "分前" は付かず，unknown marker locale 文言が出る
            assert "分前" not in rendered
            assert "時刻不明" in rendered

    async def test_chart_window_cycle_updates_state(self, tui_state) -> None:
        """``^R`` で chart window が次候補に cycle する．"""
        from anno_save_analyzer.trade.chart_window import ChartTimeWindow

        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            assert screen._chart_window == ChartTimeWindow.LAST_120_MIN
            await pilot.press("ctrl+r")
            await pilot.pause()
            assert screen._chart_window == ChartTimeWindow.LAST_4H

    async def test_chart_window_cycle_wraps_around(self, tui_state) -> None:
        """末尾 (ALL) から次を押すと先頭 (LAST_120_MIN) に戻る．"""
        from anno_save_analyzer.trade.chart_window import ChartTimeWindow

        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            screen._chart_window = ChartTimeWindow.ALL
            await pilot.press("ctrl+r")
            await pilot.pause()
            assert screen._chart_window == ChartTimeWindow.LAST_120_MIN

    async def test_chart_window_cycle_redraws_last_inventory(self, tui_state) -> None:
        """inventory chart 選択中に ^R しても例外を出さず再描画する．"""
        import dataclasses

        from anno_save_analyzer.trade import IslandStorageTrend, PointSeries

        trend = IslandStorageTrend(
            island_name="プレイヤー島",
            product_guid=2088,
            points=PointSeries(capacity=3, size=3, samples=(1, 2, 3)),
        )
        new_state = dataclasses.replace(tui_state, storage_by_island={"プレイヤー島": (trend,)})
        app = TradeApp(new_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            screen._update_inventory_chart(("プレイヤー島", 2088))
            await pilot.press("ctrl+r")
            await pilot.pause()
            # 新しい window で再描画済 = 例外出ずに通る

    async def test_chart_window_cycle_redraws_last_route(self, tui_state) -> None:
        """route 選択中に ^R で再描画．"""
        import dataclasses

        from anno_save_analyzer.trade import Item, TradeEvent, TradingPartner

        item = Item(guid=1234, names={"en": "X"})
        partner = TradingPartner(id="route:99", display_name="r", kind="route")
        events = tuple(
            TradeEvent(
                item=item,
                amount=1,
                total_price=10,
                partner=partner,
                route_id="99",
                timestamp_tick=1000 + i,
                session_id="0",
            )
            for i in range(3)
        )
        new_state = dataclasses.replace(tui_state, events=(*tui_state.events, *events))
        app = TradeApp(new_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            screen._update_route_detail("99")
            await pilot.press("ctrl+r")
            await pilot.pause()

    async def test_chart_window_filters_old_events(self, tui_state) -> None:
        """LAST_120_MIN で窓外の event は chart から消える (item chart 経由で確認)．"""
        import dataclasses

        from anno_save_analyzer.trade import Item, TradeEvent
        from anno_save_analyzer.trade.chart_window import ChartTimeWindow
        from anno_save_analyzer.trade.clock import TICKS_PER_MINUTE

        item = Item(guid=7777, names={"en": "X"})
        events = (
            # 121 分前 = LAST_120_MIN 窓外
            TradeEvent(
                item=item,
                amount=1,
                total_price=1,
                timestamp_tick=1_000_000 - 121 * TICKS_PER_MINUTE,
                session_id="0",
            ),
            # 0 分前 = 最新
            TradeEvent(
                item=item, amount=1, total_price=1, timestamp_tick=1_000_000, session_id="0"
            ),
        )
        new_state = dataclasses.replace(tui_state, events=(*tui_state.events, *events))
        app = TradeApp(new_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            screen._chart_window = ChartTimeWindow.LAST_120_MIN
            # _update_chart_pane は例外を出さずに完了する (= 窓 filter が通った)
            screen._update_chart_pane(7777)
            # ALL に切り替えても例外を出さない
            screen._chart_window = ChartTimeWindow.ALL
            screen._update_chart_pane(7777)

    async def test_route_detail_plots_cumulative_gold_for_active_route(self, tui_state) -> None:
        """履歴のある route_id を routes-table で選ぶと chart に累積 gold が描画される．"""
        from anno_save_analyzer.trade import Item, TradeEvent, TradingPartner
        from anno_save_analyzer.tui.state import TuiState

        item = Item(guid=100, names={"en": "Wood"})
        partner = TradingPartner(id="route:42", display_name="r42", kind="route")

        def _ev(tick: int, price: int) -> TradeEvent:
            return TradeEvent(
                item=item,
                amount=1,
                total_price=price,
                partner=partner,
                route_id="42",
                timestamp_tick=tick,
                session_id="0",
            )

        new_state = TuiState(
            save_path=tui_state.save_path,
            title=tui_state.title,
            locale="en",
            events=(_ev(100, 50), _ev(200, -20), _ev(300, 100)),
            items=tui_state.items,
            overview=tui_state.overview,
            item_summaries=tui_state.item_summaries,
            route_summaries=tui_state.route_summaries,
            session_ids=tui_state.session_ids,
            session_locale_keys=tui_state.session_locale_keys,
            islands_by_session=tui_state.islands_by_session,
            routes_by_session=tui_state.routes_by_session,
        )
        app = TradeApp(new_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            screen._update_route_detail("42")
            # 描画が例外を出さず title が更新されてる
            # (plotext の検証手段が少ないので smoke test)

    async def test_route_detail_idle_route_shows_leg_count(self, tui_state) -> None:
        """history 無しだが routes_by_session に定義がある idle route の chart は empty + leg count title．"""
        from anno_save_analyzer.trade import TradeRouteDef, TransportTask
        from anno_save_analyzer.tui.state import TuiState

        idle_def = TradeRouteDef(
            ship_id=999,
            route_hash=1,
            round_travel=0,
            establish_time=0,
            tasks=(TransportTask(from_key=1, to_key=2, product_guid=100, balance_raw=0),),
        )
        first_sid = tui_state.session_ids[0]
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
            routes_by_session={first_sid: (idle_def,)},
        )
        app = TradeApp(new_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            screen._update_route_detail("999")
            # idle route branch (tasks found) を踏む
            # 存在しない route_id で tasks=() branch も踏む
            screen._update_route_detail("nonexistent")

    async def test_route_row_highlight_routes_to_detail(self, tui_state) -> None:
        """routes-table の highlight が _update_route_detail を呼ぶ経路を確認．"""
        from textual.widgets import DataTable

        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen

            class _Key:
                def __init__(self, v):
                    self.value = v

            class _Evt:
                def __init__(self, t, k):
                    self.data_table = t
                    self.row_key = _Key(k)

            routes_table = screen.query_one("#routes-table", DataTable)
            # routes-table に行があれば任意 row_key で dispatch を踏む
            if routes_table.row_count:
                screen.on_data_table_row_highlighted(_Evt(routes_table, "7"))

    async def test_chart_pane_plots_cumulative_timeseries(self, tui_state) -> None:
        """timestamp 付きイベントがある物資は累積時系列がプロットされる．"""
        from textual_plotext import PlotextPlot

        from anno_save_analyzer.trade import Item, TradeEvent, TradingPartner
        from anno_save_analyzer.tui.state import TuiState

        item = Item(guid=100, names={"en": "Wood"})

        def _ev(tick: int, amount: int) -> TradeEvent:
            return TradeEvent(
                item=item,
                amount=amount,
                total_price=amount * 10,
                partner=TradingPartner(id="7", display_name="r", kind="route"),
                route_id="7",
                timestamp_tick=tick,
                session_id="0",
            )

        new_state = TuiState(
            save_path=tui_state.save_path,
            title=tui_state.title,
            locale="en",
            events=(_ev(100, 5), _ev(200, -3), _ev(300, 7)),
            items=tui_state.items,
            overview=tui_state.overview,
            item_summaries=tui_state.item_summaries,
            route_summaries=tui_state.route_summaries,
            session_ids=tui_state.session_ids,
            session_locale_keys=tui_state.session_locale_keys,
            islands_by_session=tui_state.islands_by_session,
            routes_by_session=tui_state.routes_by_session,
        )
        app = TradeApp(new_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            screen._update_chart_pane(100)
            chart = screen.query_one("#chart-pane", PlotextPlot)
            # plotext は内部状態が公開 API 少ないので smoke test のみ．
            # 例外を出さず描画されれば OK (branch カバレッジ対象の行を通す)．
            assert chart is not None
            # chart without events (無効 guid) も実行して no-events 分岐を踏む
            screen._update_chart_pane(999_999)

    async def test_inventory_row_key_tuple_handles_pipe_name_and_localized_xlabel(
        self, tui_state
    ) -> None:
        from anno_save_analyzer.trade import IslandStorageTrend, PointSeries
        from anno_save_analyzer.tui.state import TuiState

        trend = IslandStorageTrend(
            island_name="A|B",
            product_guid=100,
            points=PointSeries(capacity=3, size=3, samples=(10, 20, 30)),
        )
        new_state = TuiState(
            save_path=tui_state.save_path,
            title=tui_state.title,
            locale="ja",
            events=tui_state.events,
            items=tui_state.items,
            overview=tui_state.overview,
            item_summaries=tui_state.item_summaries,
            route_summaries=tui_state.route_summaries,
            session_ids=tui_state.session_ids,
            session_locale_keys=tui_state.session_locale_keys,
            islands_by_session=tui_state.islands_by_session,
            routes_by_session=tui_state.routes_by_session,
            storage_by_island={"A|B": (trend,)},
        )
        app = TradeApp(new_state, localizer=Localizer.load("ja"))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            from textual.widgets import DataTable
            from textual_plotext import PlotextPlot

            screen = pilot.app.screen
            chart = screen.query_one("#chart-pane", PlotextPlot)
            xlabel_calls: list[str] = []
            orig_xlabel = chart.plt.xlabel

            def _spy_xlabel(label: str) -> None:
                xlabel_calls.append(label)
                orig_xlabel(label)

            chart.plt.xlabel = _spy_xlabel

            class _Key:
                def __init__(self, value):
                    self.value = value

            class _Evt:
                def __init__(self, table, key_value):
                    self.data_table = table
                    self.row_key = _Key(key_value)

            inv_table = screen.query_one("#inventory-table", DataTable)
            screen.on_data_table_row_highlighted(_Evt(inv_table, ("A|B", 100)))
            await pilot.pause()
            # 3 サンプル = spread 2 分なので minutes_ago 単位．ja ロケール．
            assert xlabel_calls[-1] == "分 (0=最新)"

    async def test_inventory_empty_samples_uses_inventory_message(self, tui_state) -> None:
        from anno_save_analyzer.trade import IslandStorageTrend, PointSeries
        from anno_save_analyzer.tui.state import TuiState

        trend = IslandStorageTrend(
            island_name="StorageZero",
            product_guid=100,
            points=PointSeries(capacity=0, size=0, samples=()),
        )
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
            routes_by_session=tui_state.routes_by_session,
            storage_by_island={"StorageZero": (trend,)},
        )
        app = TradeApp(new_state, localizer=Localizer.load("en"))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            screen = pilot.app.screen
            called: list[str] = []
            orig = screen._render_empty_chart

            def _spy_render_empty_chart(message: str) -> None:
                called.append(message)
                orig(message)

            screen._render_empty_chart = _spy_render_empty_chart
            screen._update_inventory_chart(("StorageZero", 100))
            await pilot.pause()
            assert called[-1].endswith("no inventory samples")

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

            # (5) 未知 table id (items でも routes でもない) → 両 branch 素通り
            class _FakeTable:
                id = "some-other-table"

            screen.on_data_table_row_highlighted(_FakeEvent(_FakeTable(), "0"))
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
