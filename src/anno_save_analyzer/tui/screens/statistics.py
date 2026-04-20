"""Trade Statistics 画面．3 カラム: Tree / DataTable / (Partners + Chart)．"""

from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Static,
    TabbedContent,
    TabPane,
    Tree,
)
from textual_plotext import PlotextPlot

from anno_save_analyzer.trade import by_item, by_route, partners_for_item
from anno_save_analyzer.trade.aggregate import (
    ItemSummary,
    PartnerSummary,
    RouteSummary,
    filter_events,
)
from anno_save_analyzer.trade.models import TradeEvent

from ..i18n import Localizer
from ..sparkline import sparkline
from ..state import TuiState


@dataclass(frozen=True)
class TradeFilter:
    """Tree 選択から派生する集計フィルタ．両方 None なら全体．"""

    session: str | None = None
    island: str | None = None

    @property
    def is_all(self) -> bool:
        return self.session is None and self.island is None


class TradeStatisticsScreen(Screen):
    """3 カラム統計画面．右端は Partners pane (上) + 時系列 Chart (下) を縦分割．"""

    DEFAULT_CSS = """
    TradeStatisticsScreen Horizontal {
        height: 1fr;
    }
    TradeStatisticsScreen Tree {
        width: 28;
        border: solid $secondary;
    }
    TradeStatisticsScreen TabbedContent {
        width: 1fr;
        border: solid $secondary;
    }
    TradeStatisticsScreen #right-column {
        width: 42;
    }
    TradeStatisticsScreen #partners-pane {
        height: 40%;
        border: solid $secondary;
    }
    TradeStatisticsScreen #chart-pane {
        height: 60%;
        border: solid $secondary;
    }
    """

    def __init__(self, state: TuiState, localizer: Localizer) -> None:
        super().__init__(name="statistics")
        self._state = state
        self._localizer = localizer
        self._filter = TradeFilter()
        self._filtered_events_cache: list[TradeEvent] | None = None
        self._filtered_events_cache_key: tuple[str | None, str | None] | None = None

    def set_localizer(self, localizer: Localizer) -> None:
        """``TradeApp.switch_locale`` から呼ばれる公開 setter．

        ``_localizer`` の直書き回避．再描画はコール側の ``refresh(recompose=True)``
        に委譲する．
        """
        self._localizer = localizer

    def compose(self) -> ComposeResult:
        t = self._localizer.t
        yield Header()
        yield Static(self._filter_label(), id="filter-banner")
        with Horizontal():
            yield self._render_tree()
            with TabbedContent(id="stats-tabs"):
                with TabPane(t("statistics.tab.items"), id="items-tab"):
                    yield self._render_items_table()
                with TabPane(t("statistics.tab.routes"), id="routes-tab"):
                    yield self._render_routes_table()
                with TabPane(t("statistics.tab.inventory"), id="inventory-tab"):
                    yield self._render_inventory_table()
            with Vertical(id="right-column"):
                yield Static(
                    f"[b]{t('partners.heading')}[/b]\n\n{t('partners.empty')}",
                    id="partners-pane",
                )
                yield PlotextPlot(id="chart-pane")
        yield Footer()

    def _render_tree(self) -> Tree:
        t = self._localizer.t
        # root の data=None は「All = フィルタ解除」を意味する
        tree = Tree[TradeFilter | None](t("statistics.tree_root"), id="sessions-tree")
        tree.root.data = None
        tree.root.expand()
        keys = self._state.session_locale_keys or tuple(
            "session.unknown" for _ in self._state.session_ids
        )
        islands_by_sid = self._state.islands_by_session
        for sid, key in zip(self._state.session_ids, keys, strict=False):
            session_node = tree.root.add(
                t(key, index=sid),
                expand=True,
                data=TradeFilter(session=sid),
            )
            for island in islands_by_sid.get(sid, ()):
                session_node.add_leaf(
                    island.city_name,
                    data=TradeFilter(session=sid, island=island.city_name),
                )
        return tree

    def _filter_label(self) -> str:
        """Footer 上の帯に出す現 filter 説明．``All`` 時は空気に近い表示．"""
        t = self._localizer.t
        if self._filter.is_all:
            return t("statistics.filter.all")
        if self._filter.island is not None:
            return t("statistics.filter.island", name=self._filter.island)
        # session のみ
        sid = self._filter.session or ""
        locale_key = next(
            (
                k
                for s, k in zip(
                    self._state.session_ids, self._state.session_locale_keys, strict=False
                )
                if s == sid
            ),
            "session.unknown",
        )
        return t("statistics.filter.session", name=t(locale_key, index=sid))

    def _filtered_events(self) -> list:
        """現在の ``self._filter`` を適用した events．"""
        key = (self._filter.session, self._filter.island)
        if self._filtered_events_cache_key == key and self._filtered_events_cache is not None:
            return self._filtered_events_cache
        self._filtered_events_cache = filter_events(
            self._state.events, session=self._filter.session, island=self._filter.island
        )
        self._filtered_events_cache_key = key
        return self._filtered_events_cache

    def _current_item_summaries(self) -> tuple[ItemSummary, ...]:
        """TuiState の pre-computed と同値．``_filter.is_all`` なら cache 再利用．"""
        if self._filter.is_all:
            return self._state.item_summaries
        return tuple(by_item(self._filtered_events()))

    def _current_route_summaries(self) -> tuple[RouteSummary, ...]:
        if self._filter.is_all:
            return self._state.route_summaries
        return tuple(by_route(self._filtered_events()))

    def _render_items_table(self) -> DataTable:
        table = DataTable(id="items-table")
        table.cursor_type = "row"
        t = self._localizer.t
        table.add_columns(
            t("statistics.col.good"),
            t("statistics.col.bought"),
            t("statistics.col.sold"),
            t("statistics.col.net_qty"),
            t("statistics.col.net_gold"),
            t("statistics.col.events"),
            t("statistics.col.trend"),
        )
        # 各物資の累積数量 sparkline を先に算出．1 物資 = 1 sparkline string．
        trends = self._build_item_trends()
        for s in self._current_item_summaries():
            row = (*self._format_item_row(s), trends.get(s.item.guid, ""))
            table.add_row(*row, key=str(s.item.guid))
        return table

    def _build_item_trends(self) -> dict[int, str]:
        """item GUID → 累積数量 sparkline 文字列 (width=12)．

        timestamp を持つイベントのみ対象に，時刻昇順で累積を取る．
        現在の filter が有効なら pre-filter．
        """
        events = self._filtered_events() if not self._filter.is_all else self._state.events
        series: dict[int, list[tuple[int, int]]] = {}
        for ev in events:
            if ev.timestamp_tick is None:
                continue
            series.setdefault(ev.item.guid, []).append((ev.timestamp_tick, ev.amount))
        out: dict[int, str] = {}
        for guid, rows in series.items():
            rows.sort(key=lambda r: r[0])
            cumulative: list[int] = []
            running = 0
            for _tick, amt in rows:
                running += amt
                cumulative.append(running)
            out[guid] = sparkline(cumulative)
        return out

    def _render_routes_table(self) -> DataTable:
        table = DataTable(id="routes-table")
        t = self._localizer.t
        table.add_columns(
            t("statistics.col.route"),
            t("statistics.col.status"),
            t("statistics.col.kind"),
            t("statistics.col.legs"),
            t("statistics.col.bought"),
            t("statistics.col.sold"),
            t("statistics.col.net_gold"),
            t("statistics.col.events"),
        )
        route_summaries = self._current_route_summaries()
        active_ids: set[str] = {s.route_id for s in route_summaries if s.route_id is not None}
        legs_by_ship: dict[str, int] = {}
        # idle routes は session filter 効くが island filter は不明 (route 定義には
        # island 情報が載らない)．filter 時は history 既知の route 以外 hide する．
        sessions_in_scope = (
            (self._filter.session,)
            if self._filter.session is not None
            else tuple(self._state.routes_by_session)
        )
        for sid in sessions_in_scope:
            for rd in self._state.routes_by_session.get(sid, ()):
                if rd.ship_id is not None:
                    legs_by_ship[str(rd.ship_id)] = len(rd.tasks)

        # active routes (履歴あり) を先に，次に idle (定義あり / 履歴無し)
        # row_key = route_id (str) で後段の highlight event から参照できるようにする．
        for s in route_summaries:
            legs = legs_by_ship.get(s.route_id or "", 0) if s.route_id else 0
            row_key = s.route_id if s.route_id is not None else None
            table.add_row(*self._format_route_row(s, legs, active=True), key=row_key)
        # island filter 時は idle route 情報源 (route 定義) に island が無いので
        # 全部 hide．session filter だけの場合は当該 session のみ出す．
        if self._filter.island is not None:
            return table
        for sid in sessions_in_scope:
            routes = self._state.routes_by_session.get(sid, ())
            for rd in routes:
                if rd.ship_id is None:
                    continue
                rid = str(rd.ship_id)
                if rid in active_ids:
                    continue
                table.add_row(*self._format_idle_route_row(rd), key=rid)
                active_ids.add(rid)  # 同一 ship_id が他 session に出ても 2 重計上しない
        return table

    def _format_item_row(self, s: ItemSummary) -> tuple[str, ...]:
        return (
            s.display_name(self._localizer.code),
            f"{s.bought:,}",
            f"{s.sold:,}",
            f"{s.net_qty:+,}",
            f"{s.net_gold:+,}",
            f"{s.event_count:,}",
        )

    def _current_inventory_rows(self):
        """現在の ``_filter`` を Inventory 表示用の (島, trend) 列に落とす．

        island filter → その島のみ / session filter → 当該 session の島 /
        filter 無し → 全島を連結．``IslandStorageTrend`` は session 情報を持たない
        ので session filter は ``islands_by_session`` からその session の島名
        集合を引いて交差を取る．
        """
        storage = self._state.storage_by_island
        if self._filter.island is not None:
            names = {self._filter.island}
        elif self._filter.session is not None:
            islands = self._state.islands_by_session.get(self._filter.session, ())
            names = {i.city_name for i in islands}
        else:
            names = set(storage)
        rows: list = []
        for name in sorted(names):
            rows.extend(storage.get(name, ()))
        return rows

    def _render_inventory_table(self) -> DataTable:
        table = DataTable(id="inventory-table")
        table.cursor_type = "row"
        t = self._localizer.t
        table.add_columns(
            t("statistics.col.island"),
            t("statistics.col.good"),
            t("statistics.col.latest"),
            t("statistics.col.peak"),
            t("statistics.col.mean"),
            t("statistics.col.slope"),
            t("statistics.col.trend"),
        )
        for tr in self._current_inventory_rows():
            table.add_row(
                *self._format_inventory_row(tr), key=f"{tr.island_name}|{tr.product_guid}"
            )
        return table

    def _format_inventory_row(self, tr) -> tuple[str, ...]:
        item = self._state.items[tr.product_guid]
        return (
            tr.island_name,
            item.display_name(self._localizer.code),
            f"{tr.latest:,}",
            f"{tr.peak:,}",
            f"{tr.points.mean:,.0f}",
            f"{tr.points.slope:+.2f}",
            sparkline(tr.points.samples, width=12),
        )

    def _format_route_row(self, s: RouteSummary, legs: int, *, active: bool) -> tuple[str, ...]:
        t = self._localizer.t
        route_id = s.route_id if s.route_id is not None else "—"
        status = t("statistics.status.active") if active else t("statistics.status.idle")
        return (
            route_id,
            status,
            s.partner_kind,
            f"{legs:,}",
            f"{s.bought:,}",
            f"{s.sold:,}",
            f"{s.net_gold:+,}",
            f"{s.event_count:,}",
        )

    def _format_idle_route_row(self, rd) -> tuple[str, ...]:
        t = self._localizer.t
        return (
            str(rd.ship_id),
            t("statistics.status.idle"),
            "route",
            f"{len(rd.tasks):,}",
            "0",
            "0",
            "+0",
            "0",
        )

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Tree のノード選択で ``self._filter`` を更新し，画面を作り直す．

        - root: data=None → filter reset (All)
        - session node: data=TradeFilter(session=sid)
        - island leaf: data=TradeFilter(session=sid, island=city)
        """
        data = event.node.data
        new_filter: TradeFilter = data if isinstance(data, TradeFilter) else TradeFilter()
        if new_filter == self._filter:
            return
        self._filter = new_filter
        self._filtered_events_cache = None
        self._filtered_events_cache_key = None
        self.refresh(recompose=True)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """items / routes / inventory テーブルの行 highlight で右 pane を更新．"""
        table_id = event.data_table.id
        row_key = event.row_key.value if event.row_key is not None else None
        if not row_key:
            return
        if table_id == "inventory-table":
            self._update_inventory_chart(row_key)
            return
        if table_id == "items-table":
            try:
                guid = int(row_key)
            except ValueError:
                return
            self._update_partners_pane(guid)
        elif table_id == "routes-table":
            self._update_route_detail(row_key)

    def _update_partners_pane(self, item_guid: int) -> None:
        rows = partners_for_item(
            self._state.events,
            item_guid,
            session=self._filter.session,
            island=self._filter.island,
        )
        self.query_one("#partners-pane", Static).update(self._format_partners_pane(rows, item_guid))
        self._update_chart_pane(item_guid)

    def _update_chart_pane(self, item_guid: int) -> None:
        """選択物資の取引を (timestamp_tick, 累積数量) の折れ線で描画．"""
        t = self._localizer.t
        scoped = self._filtered_events() if not self._filter.is_all else self._state.events
        events = sorted(
            (e for e in scoped if e.item.guid == item_guid and e.timestamp_tick is not None),
            key=lambda e: e.timestamp_tick or 0,
        )
        item = self._state.items[item_guid]
        title = item.display_name(self._localizer.code)
        if not events:
            self._render_empty_chart(t("statistics.chart.no_timed_events", title=title))
            return
        x_values, y_values, unit_key = self._cumulative_series(events, by="amount")
        self._plot_line(
            title,
            x_values,
            y_values,
            ylabel=t("statistics.chart.ylabel.cumulative_qty"),
            unit_key=unit_key,
        )

    def _update_route_detail(self, route_id: str) -> None:
        """選択ルートの累積 net gold 時系列を chart pane に描画．"""
        scoped = self._filtered_events() if not self._filter.is_all else self._state.events
        events = sorted(
            (e for e in scoped if e.route_id == route_id and e.timestamp_tick is not None),
            key=lambda e: e.timestamp_tick or 0,
        )
        t = self._localizer.t
        title = f"{t('statistics.col.route')} #{route_id}"
        if not events:
            # idle route: 履歴なし．定義 leg を簡潔に表示．
            idle_tasks = self._find_idle_route_tasks(route_id)
            if idle_tasks:
                title = (
                    f"{title} "
                    f"({t('statistics.chart.idle_suffix', status=t('statistics.status.idle'), legs=len(idle_tasks))})"
                )
            self._render_empty_chart(t("statistics.chart.no_timed_events", title=title))
            return
        x_values, y_values, unit_key = self._cumulative_series(events, by="total_price")
        self._plot_line(
            title,
            x_values,
            y_values,
            ylabel=t("statistics.chart.ylabel.cumulative_gold"),
            unit_key=unit_key,
        )

    def _update_inventory_chart(self, row_key: str) -> None:
        """inventory-table 選択時に Points 時系列を chart pane に描画．

        row_key は ``f"{island}|{guid}"`` 形式．
        """
        t = self._localizer.t
        if "|" not in row_key:
            return
        island, guid_str = row_key.rsplit("|", 1)
        try:
            guid = int(guid_str)
        except ValueError:
            return
        trend = next(
            (tr for tr in self._state.storage_by_island.get(island, ()) if tr.product_guid == guid),
            None,
        )
        if trend is None:
            return
        item = self._state.items[guid]
        title = f"{island} · {item.display_name(self._localizer.code)}"
        samples = list(trend.points.samples)
        if not samples:
            self._render_empty_chart(t("statistics.chart.no_timed_events", title=title))
            return
        x_values = list(range(len(samples)))
        chart = self.query_one("#chart-pane", PlotextPlot)
        chart.plt.clear_data()
        chart.plt.clear_figure()
        chart.plt.plot(x_values, samples, marker="hd")
        chart.plt.title(title)
        chart.plt.xlabel("sample index")
        chart.plt.ylabel(t("statistics.col.latest"))
        chart.refresh()

    def _find_idle_route_tasks(self, route_id: str) -> tuple:
        """routes_by_session から ship_id 一致の TradeRouteDef を探し tasks を返す．"""
        for routes in self._state.routes_by_session.values():
            for rd in routes:
                if rd.ship_id is not None and str(rd.ship_id) == route_id:
                    return rd.tasks
        return ()

    def _cumulative_series(self, events, *, by: str) -> tuple[list[float], list[int], str]:
        """events を時刻昇順で累積．x 軸は「最新 event を 0 とした相対時間 (負)」．

        spread に応じて分 / 時間を auto 切替する．返り値の 3 つ目は xlabel の
        locale key suffix ("minutes_ago" / "hours_ago")．
        """
        from anno_save_analyzer.trade.clock import (
            latest_tick,
            minutes_relative_to,
            pick_time_unit,
        )

        ticks = [e.timestamp_tick for e in events if e.timestamp_tick is not None]
        now = latest_tick(ticks) or 0
        minutes = [minutes_relative_to(e.timestamp_tick or 0, now_tick=now) for e in events]
        unit_key, divisor = pick_time_unit(minutes)
        x_values = [m * divisor for m in minutes]
        y_values: list[int] = []
        running = 0
        for e in events:
            running += e.amount if by == "amount" else e.total_price
            y_values.append(running)
        return x_values, y_values, unit_key

    def _plot_line(
        self, title: str, x: list[float], y: list[int], *, ylabel: str, unit_key: str
    ) -> None:
        chart = self.query_one("#chart-pane", PlotextPlot)
        t = self._localizer.t
        chart.plt.clear_data()
        chart.plt.clear_figure()
        chart.plt.plot(x, y, marker="hd")
        chart.plt.title(title)
        chart.plt.xlabel(t(f"statistics.chart.xlabel.{unit_key}"))
        chart.plt.ylabel(ylabel)
        chart.refresh()

    def _render_empty_chart(self, title: str) -> None:
        chart = self.query_one("#chart-pane", PlotextPlot)
        chart.plt.clear_data()
        chart.plt.clear_figure()
        chart.plt.title(title)
        chart.refresh()

    def _format_partners_pane(self, rows: list[PartnerSummary], item_guid: int) -> str:
        t = self._localizer.t
        if not rows:
            item = self._state.items[item_guid]
            return (
                f"[b]{t('partners.heading')}[/b]\n\n"
                f"[dim]{item.display_name(self._localizer.code)}[/dim]\n\n"
                f"{t('partners.empty')}"
            )
        item = rows[0].item
        locale = self._localizer.code
        lines: list[str] = [
            f"[b]{t('partners.heading')}[/b]",
            f"[dim]{item.display_name(locale)}[/dim]",
            "",
        ]
        for r in rows:
            lines.append(
                f"• {r.display_partner}  [dim]({r.partner_kind})[/dim]\n"
                f"    {t('statistics.col.bought')}: {r.bought:,}  "
                f"{t('statistics.col.sold')}: {r.sold:,}  "
                f"{t('statistics.col.net_gold')}: {r.net_gold:+,}  "
                f"{t('statistics.col.events')}: {r.event_count:,}"
            )
        return "\n".join(lines)
