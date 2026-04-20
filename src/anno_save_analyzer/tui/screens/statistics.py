"""Trade Statistics 画面．3 カラム: Tree / DataTable / (Partners + Chart)．"""

from __future__ import annotations

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

from anno_save_analyzer.trade import partners_for_item
from anno_save_analyzer.trade.aggregate import ItemSummary, PartnerSummary, RouteSummary

from ..i18n import Localizer
from ..sparkline import sparkline
from ..state import TuiState


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

    def compose(self) -> ComposeResult:
        t = self._localizer.t
        yield Header()
        with Horizontal():
            yield self._render_tree()
            with TabbedContent(id="stats-tabs"):
                with TabPane(t("statistics.tab.items"), id="items-tab"):
                    yield self._render_items_table()
                with TabPane(t("statistics.tab.routes"), id="routes-tab"):
                    yield self._render_routes_table()
            with Vertical(id="right-column"):
                yield Static(
                    f"[b]{t('partners.heading')}[/b]\n\n{t('partners.empty')}",
                    id="partners-pane",
                )
                yield PlotextPlot(id="chart-pane")
        yield Footer()

    def _render_tree(self) -> Tree:
        t = self._localizer.t
        tree = Tree(t("statistics.tree_root"), id="sessions-tree")
        tree.root.expand()
        keys = self._state.session_locale_keys or tuple(
            "session.unknown" for _ in self._state.session_ids
        )
        islands_by_sid = self._state.islands_by_session
        for sid, key in zip(self._state.session_ids, keys, strict=False):
            session_node = tree.root.add(t(key, index=sid), expand=True)
            for island in islands_by_sid.get(sid, ()):
                session_node.add_leaf(island.city_name)
        return tree

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
        for s in self._state.item_summaries:
            row = (*self._format_item_row(s), trends.get(s.item.guid, ""))
            table.add_row(*row, key=str(s.item.guid))
        return table

    def _build_item_trends(self) -> dict[int, str]:
        """item GUID → 累積数量 sparkline 文字列 (width=12)．

        timestamp を持つイベントのみ対象に，時刻昇順で累積を取る．
        """
        series: dict[int, list[tuple[int, int]]] = {}
        for ev in self._state.events:
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
        active_ids: set[str] = {
            s.route_id for s in self._state.route_summaries if s.route_id is not None
        }
        legs_by_ship: dict[str, int] = {}
        for routes in self._state.routes_by_session.values():
            for rd in routes:
                if rd.ship_id is not None:
                    legs_by_ship[str(rd.ship_id)] = len(rd.tasks)

        # active routes (履歴あり) を先に，次に idle (定義あり / 履歴無し)
        # row_key = route_id (str) で後段の highlight event から参照できるようにする．
        for s in self._state.route_summaries:
            legs = legs_by_ship.get(s.route_id or "", 0) if s.route_id else 0
            row_key = s.route_id if s.route_id is not None else None
            table.add_row(*self._format_route_row(s, legs, active=True), key=row_key)
        for routes in self._state.routes_by_session.values():
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

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """items / routes テーブル双方の行 highlight で右 pane を更新．"""
        table_id = event.data_table.id
        row_key = event.row_key.value if event.row_key is not None else None
        if not row_key:
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
        rows = partners_for_item(self._state.events, item_guid)
        self.query_one("#partners-pane", Static).update(self._format_partners_pane(rows, item_guid))
        self._update_chart_pane(item_guid)

    def _update_chart_pane(self, item_guid: int) -> None:
        """選択物資の取引を (timestamp_tick, 累積数量) の折れ線で描画．"""
        t = self._localizer.t
        events = sorted(
            (
                e
                for e in self._state.events
                if e.item.guid == item_guid and e.timestamp_tick is not None
            ),
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
        events = sorted(
            (
                e
                for e in self._state.events
                if e.route_id == route_id and e.timestamp_tick is not None
            ),
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
