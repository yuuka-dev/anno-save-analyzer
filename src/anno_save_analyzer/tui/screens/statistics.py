"""Trade Statistics 画面．3 カラム: Tree / DataTable / (Partners + Chart)．"""

from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    OptionList,
    Static,
    TabbedContent,
    TabPane,
    Tree,
)
from textual.widgets.option_list import Option
from textual_plotext import PlotextPlot

from anno_save_analyzer.trade import (
    by_item,
    by_route,
    events_for_item,
    partners_for_item,
)
from anno_save_analyzer.trade import chart_window as chart_window_mod
from anno_save_analyzer.trade.aggregate import (
    ItemSummary,
    PartnerSummary,
    RouteSummary,
    filter_events,
)
from anno_save_analyzer.trade.chart_window import ChartTimeWindow
from anno_save_analyzer.trade.clock import TICKS_PER_MINUTE, latest_tick
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


# ``^P`` パレットに並ぶ選択肢．(locale key, value) のペア．
# value=None は「全期間」．分単位の数値はそのまま ``max_age_minutes`` に流し込む．
_RECENT_WINDOW_OPTIONS: tuple[tuple[str, float | None], ...] = (
    ("partners.recent_window.all", None),
    ("partners.recent_window.minutes", 60.0),
    ("partners.recent_window.minutes", 120.0),
    ("partners.recent_window.minutes", 360.0),
    ("partners.recent_window.hours", 1440.0),
)


class RecentWindowPalette(ModalScreen[float | None]):
    """``^P`` で開く直近取引の時間窓選択モーダル．

    ``dismiss`` の返り値 = 選択された ``max_age_minutes`` (``None`` なら全期間)．
    Esc では現在値 (``self._current``) で ``dismiss`` して閉じる．
    そのため呼び出し側では実質的に no-op として扱える．
    """

    DEFAULT_CSS = """
    RecentWindowPalette {
        align: center middle;
    }
    RecentWindowPalette > Vertical {
        width: 50;
        height: auto;
        border: solid $secondary;
        background: $surface;
        padding: 1 2;
    }
    RecentWindowPalette OptionList {
        height: auto;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_palette", show=False),
    ]

    def __init__(self, localizer: Localizer, current: float | None) -> None:
        super().__init__()
        self._localizer = localizer
        self._current = current

    def compose(self) -> ComposeResult:
        t = self._localizer.t
        options: list[Option] = []
        for key, value in _RECENT_WINDOW_OPTIONS:
            if value is None:
                label = t(key)
            elif key.endswith(".hours"):
                label = t(key, value=value / 60.0)
            else:
                label = t(key, value=value)
            if value == self._current or (value is None and self._current is None):
                label = f"[b]• {label}[/b]"
            else:
                label = f"  {label}"
            options.append(Option(label))
        with Vertical():
            yield Static(f"[b]{t('partners.recent_window_title')}[/b]")
            yield Static(f"[dim]{t('partners.recent_window.hint')}[/dim]")
            yield OptionList(*options, id="recent-window-options")

    def on_mount(self) -> None:  # pragma: no cover - textual focus wiring
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        _, value = _RECENT_WINDOW_OPTIONS[event.option_index]
        self.dismiss(value)

    def action_dismiss_palette(self) -> None:  # pragma: no cover - manual esc
        self.dismiss(self._current)


class TradeStatisticsScreen(Screen):
    """3 カラム統計画面．右端は Partners pane (上) + 時系列 Chart (下) を縦分割．"""

    BINDINGS = [
        Binding("ctrl+p", "recent_window", "History window"),
        Binding("ctrl+r", "cycle_chart_window", "Range"),
    ]

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
    TradeStatisticsScreen DataTable {
        height: 1fr;
    }
    TradeStatisticsScreen #right-column {
        width: 42;
    }
    TradeStatisticsScreen #partners-scroll {
        height: 40%;
        border: solid $secondary;
    }
    TradeStatisticsScreen #chart-pane {
        height: 60%;
        border: solid $secondary;
    }
    /* Responsive: mid (80-119 cols) では右カラムを縮めて sparkline 列は維持 */
    TradeStatisticsScreen.mid #right-column {
        width: 32;
    }
    /* Responsive: narrow (<80 cols) では Tree を縮め右カラムを完全 hide．
       Partners / Chart は ^T で Overview 往復の方が素直なので非表示で十分． */
    TradeStatisticsScreen.narrow Tree {
        width: 16;
    }
    TradeStatisticsScreen.narrow #right-column {
        display: none;
    }
    """

    # 幅の境界値 (terminal cols)．上端は含まない閉区間．
    # wide: >= 120 / mid: 80-119 / narrow: < 80
    _MID_BREAKPOINT = 120
    _NARROW_BREAKPOINT = 80

    def __init__(self, state: TuiState, localizer: Localizer) -> None:
        super().__init__(name="statistics")
        self._state = state
        self._localizer = localizer
        self._apply_localized_bindings()
        self._filter = TradeFilter()
        self._filtered_events_cache: list[TradeEvent] | None = None
        self._filtered_events_cache_key: tuple[str | None, str | None] | None = None
        self._layout_class: str | None = None
        # 直近取引セクションの時間窓 (分)．``None`` は「全期間」．``^P`` パレットで切替．
        self._recent_window_minutes: float | None = None
        # 最後に選択していた item_guid (^P で設定変更時の再描画に使う)．
        self._last_selected_item_guid: int | None = None
        # 最後に選んでいた route_id / inventory row key．^R cycle で再描画に使う．
        self._last_selected_route_id: str | None = None
        self._last_selected_inventory_key: tuple[str, int] | None = None
        # チャート描画の時間窓．書記長希望のデフォルト 120 分．``^R`` で cycle．
        self._chart_window: ChartTimeWindow = ChartTimeWindow.LAST_120_MIN

    def _classify_width(self, width: int) -> str:
        """terminal 幅から layout class を選ぶ (wide / mid / narrow)．"""
        if width < self._NARROW_BREAKPOINT:
            return "narrow"
        if width < self._MID_BREAKPOINT:
            return "mid"
        return "wide"

    def _apply_layout_class(self, width: int) -> bool:
        """幅から layout class を決定し，screen に付け替える．

        変わったら True を返す．compose 直後と resize 時に呼ぶ．
        wide / mid / narrow の 3 択はいずれも明示的に class 付与 (CSS の
        ``TradeStatisticsScreen.narrow ...`` のような選択子と対応させるため)．
        """
        new_cls = self._classify_width(width)
        if new_cls == self._layout_class:
            return False
        for cls in ("wide", "mid", "narrow"):
            self.remove_class(cls)
        self.add_class(new_cls)
        self._layout_class = new_cls
        return True

    def set_localizer(self, localizer: Localizer) -> None:
        """``TradeApp.switch_locale`` から呼ばれる公開 setter．

        ``_localizer`` の直書き回避．再描画はコール側の ``refresh(recompose=True)``
        に委譲する．
        """
        self._localizer = localizer
        self._apply_localized_bindings()

    def _apply_localized_bindings(self) -> None:
        self.BINDINGS = [
            Binding("ctrl+p", "recent_window", self._localizer.t("binding.recent_window")),
            Binding("ctrl+r", "cycle_chart_window", self._localizer.t("binding.chart_window")),
        ]
        self.refresh_bindings()

    def action_recent_window(self) -> None:
        """``^P``: 直近取引の時間窓を選ぶパレットを開く．"""
        self.app.push_screen(
            RecentWindowPalette(self._localizer, self._recent_window_minutes),
            self._on_recent_window_chosen,
        )

    def _on_recent_window_chosen(self, value: float | None) -> None:
        """パレットから返ってきた値を適用し，必要なら Partners pane を再描画．

        現行と同一なら no-op (notify も出さない)．Esc キャンセルは同値経由で
        ここに来るので自然に弾かれる．
        """
        if value == self._recent_window_minutes:
            return
        self._recent_window_minutes = value
        self._notify_recent_window(value)
        if self._last_selected_item_guid is not None:
            self._update_partners_pane(self._last_selected_item_guid)
        self._request_persist()

    def _request_persist(self) -> None:
        """app に ``persist_user_settings`` があれば呼ぶ．unit test / 単体起動でも
        crash しないよう ``getattr`` で柔らかく参照．
        """
        persist = getattr(self.app, "persist_user_settings", None)
        if persist is not None:
            persist()

    def _notify_recent_window(self, value: float | None) -> None:
        t = self._localizer.t
        if value is None:
            self.app.notify(t("partners.recent_window.notice.all"))
        elif value >= 60.0 and value % 60 == 0:
            self.app.notify(t("partners.recent_window.notice.hours", value=value / 60.0))
        else:
            self.app.notify(t("partners.recent_window.notice.minutes", value=value))

    def action_cycle_chart_window(self) -> None:
        """``^R``: chart 時間窓を次の候補に cycle + 現在選択中のチャートを再描画．"""
        self._chart_window = self._chart_window.next()
        t = self._localizer.t
        self.app.notify(t("chart.window.notice", label=t(self._chart_window.locale_key)))
        self._redraw_active_chart_window()
        self._request_persist()

    def _redraw_active_chart_window(self) -> None:
        """現在アクティブな tab に対応する chart だけ再描画する．"""
        active_tab = self.query_one("#stats-tabs", TabbedContent).active
        if active_tab == "inventory-tab" and self._last_selected_inventory_key is not None:
            self._update_inventory_chart(self._last_selected_inventory_key)
        elif active_tab == "routes-tab" and self._last_selected_route_id is not None:
            self._update_route_detail(self._last_selected_route_id)
        elif active_tab == "items-tab" and self._last_selected_item_guid is not None:
            self._update_chart_pane(self._last_selected_item_guid)

    def compose(self) -> ComposeResult:
        # Trend 列 / 右カラム hide 等の layout 判定は compose の早い段階で固める．
        # ``app.size`` は compose 呼出時に有効．on_mount で recompose する実装
        # にすると Header.mount_title タイミングと衝突するため採らない．
        self._apply_layout_class(self.app.size.width)
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
                # Partners pane は本文が長くなり得るので VerticalScroll 経由．
                # narrow layout 時はこの Vertical ごと display:none で隠れる．
                with VerticalScroll(id="partners-scroll"):
                    yield Static(
                        f"[b]{t('partners.heading')}[/b]\n\n{t('partners.empty')}",
                        id="partners-pane",
                    )
                yield PlotextPlot(id="chart-pane")
        yield Footer()

    def on_resize(self, event: events.Resize) -> None:
        """terminal 幅変更で layout class を切替 (width のみ見る)．"""
        if self._apply_layout_class(event.size.width):
            # class が変わった場合のみ再 compose．Trend 列の出し分け等も拾うため．
            self.refresh(recompose=True)

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
        # narrow layout (<80 cols) 時は Trend sparkline 列を省略．文字幅節約．
        include_trend = self._layout_class != "narrow"
        columns: list[str] = [
            t("statistics.col.good"),
            t("statistics.col.bought"),
            t("statistics.col.sold"),
            t("statistics.col.net_qty"),
            t("statistics.col.net_gold"),
            t("statistics.col.events"),
        ]
        if include_trend:
            columns.append(t("statistics.col.trend"))
        table.add_columns(*columns)
        trends = self._build_item_trends() if include_trend else {}
        for s in self._current_item_summaries():
            base = self._format_item_row(s)
            row = (*base, trends.get(s.item.guid, "")) if include_trend else base
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
        """現在の ``_filter`` に対応する ``IslandStorageTrend`` の一覧を返す．

        island filter → その島のみ / session filter → 当該 session の島 /
        filter 無し → 全島を連結．返り値は ``(島, trend)`` の組ではなく，
        各行が島名を内包した ``IslandStorageTrend`` のフラットなリスト．
        ``IslandStorageTrend`` は session 情報を持たないので，session filter は
        ``islands_by_session`` からその session の島名集合を引いて交差を取る．
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
            table.add_row(*self._format_inventory_row(tr), key=(tr.island_name, tr.product_guid))
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
        status = t("statistics.status.active") if active else t("statistics.status.idle")
        return (
            s.display_route,  # route_name 優先．無ければ #<route_id> or "—"
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
            f"#{rd.ship_id}",
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
        if row_key is None or row_key == "":
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
        self._last_selected_item_guid = item_guid
        rows = partners_for_item(
            self._state.events,
            item_guid,
            session=self._filter.session,
            island=self._filter.island,
        )
        text = Text.from_markup(self._format_partners_pane(rows, item_guid))
        # 直近取引行がペイン幅超えても視覚的に改行されんよう no_wrap + crop．
        # 書記長要望: 取引履歴は 1 行 = 1 イベント．溢れた分は切り落とす (スクロール
        # の cognitive load より省略の方がマシという判断)．
        text.no_wrap = True
        text.overflow = "crop"
        self.query_one("#partners-pane", Static).update(text)
        self._update_chart_pane(item_guid)

    def _chart_title_with_window(self, title: str) -> str:
        """chart タイトル末尾に現在の時間窓ラベルを ``·`` 区切りで追加．"""
        t = self._localizer.t
        return f"{title} · {t(self._chart_window.locale_key)}"

    def _update_chart_pane(self, item_guid: int) -> None:
        """選択物資の取引を (timestamp_tick, 累積数量) の折れ線で描画．"""
        t = self._localizer.t
        scoped = self._filtered_events() if not self._filter.is_all else self._state.events
        matching = [e for e in scoped if e.item.guid == item_guid and e.timestamp_tick is not None]
        windowed = chart_window_mod.filter_events(matching, self._chart_window)
        events = sorted(windowed, key=lambda e: e.timestamp_tick or 0)
        item = self._state.items[item_guid]
        title = self._chart_title_with_window(item.display_name(self._localizer.code))
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
        self._last_selected_route_id = route_id
        scoped = self._filtered_events() if not self._filter.is_all else self._state.events
        matching = [e for e in scoped if e.route_id == route_id and e.timestamp_tick is not None]
        windowed = chart_window_mod.filter_events(matching, self._chart_window)
        events = sorted(windowed, key=lambda e: e.timestamp_tick or 0)
        t = self._localizer.t
        title = self._chart_title_with_window(f"{t('statistics.col.route')} #{route_id}")
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

    def _update_inventory_chart(self, row_key: tuple[str, int] | object) -> None:
        """inventory-table 選択時に Points 時系列を chart pane に描画．

        row_key は ``(island_name, product_guid)`` の tuple を受け取る．
        """
        t = self._localizer.t
        if not (
            isinstance(row_key, tuple)
            and len(row_key) == 2
            and isinstance(row_key[0], str)
            and isinstance(row_key[1], int)
        ):
            return
        self._last_selected_inventory_key = row_key
        island, guid = row_key
        trend = next(
            (tr for tr in self._state.storage_by_island.get(island, ()) if tr.product_guid == guid),
            None,
        )
        if trend is None:
            return
        from anno_save_analyzer.trade.clock import (
            inventory_sample_minutes,
            pick_time_unit,
        )

        item = self._state.items[guid]
        title = self._chart_title_with_window(
            f"{island} · {item.display_name(self._localizer.code)}"
        )
        samples = list(trend.points.samples)
        if not samples:
            self._render_empty_chart(t("statistics.chart.no_inventory_samples", title=title))
            return
        # 最新 = 0，最古 = -(n-1) * step．chart は昇順なので左端が最古．
        minutes = inventory_sample_minutes(len(samples))
        # ``^R`` で選択中の window で区間を絞る．窓外の古い sample は描画しない．
        keep_indices, minutes = chart_window_mod.filter_inventory_minutes(
            minutes, self._chart_window
        )
        samples = [samples[i] for i in keep_indices]
        if not samples:
            self._render_empty_chart(t("statistics.chart.no_inventory_samples", title=title))
            return
        unit_key, divisor = pick_time_unit(minutes)
        x_values = [m * divisor for m in minutes]
        chart = self.query_one("#chart-pane", PlotextPlot)
        chart.plt.clear_data()
        chart.plt.clear_figure()
        chart.plt.plot(x_values, samples, marker="hd")
        chart.plt.title(title)
        chart.plt.xlabel(t(f"statistics.chart.xlabel.{unit_key}"))
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
        lines.append("")
        lines.extend(self._format_recent_trades(item_guid))
        return "\n".join(lines)

    # row 毎に「分／時間」を切り替える閾値．書記長フィードバック (#46 後続) で
    # 全体 spread 判定を捨て，個別 row の age だけで単位を決める方針に変更．
    _RECENT_ROW_HOURS_THRESHOLD_MIN = 120.0

    def _format_recent_trades(self, item_guid: int, *, limit: int = 50) -> list[str]:
        """直近取引セクションの行を生成．tick 降順 / tick=None は末尾 "時刻不明"．

        相対時間は「最新イベント tick」を基準とし，row 毎に 120 分以下なら「分」，
        超えたら「時間」に切り替えて表示する．``_recent_window_minutes`` が設定
        されていれば ``events_for_item`` にそのまま渡し古い event を除外する．
        """
        t = self._localizer.t
        recent = events_for_item(
            self._state.events,
            item_guid,
            session=self._filter.session,
            island=self._filter.island,
            limit=limit,
            max_age_minutes=self._recent_window_minutes,
        )
        header = f"[b]{t('partners.recent_heading')}[/b]"
        if not recent:
            return [header, f"[dim]{t('partners.recent_empty')}[/dim]"]
        ticks = [ev.timestamp_tick for ev in recent if ev.timestamp_tick is not None]
        now_tick = latest_tick(ticks)
        lines: list[str] = [header]
        for ev in recent:
            lines.append(self._format_recent_trade_row(ev, now_tick=now_tick))
        return lines

    def _format_recent_trade_row(self, ev: TradeEvent, *, now_tick: int | None) -> str:
        t = self._localizer.t
        if ev.timestamp_tick is None or now_tick is None:
            time_label = t("partners.recent_row.unknown")
        else:
            minutes = (now_tick - ev.timestamp_tick) / TICKS_PER_MINUTE
            if minutes > self._RECENT_ROW_HOURS_THRESHOLD_MIN:
                time_label = t("partners.recent_row.hours_ago", value=minutes / 60.0)
            else:
                time_label = t("partners.recent_row.minutes_ago", value=minutes)
        island = ev.island_name or "—"
        qty_color = "green" if ev.amount > 0 else ("red" if ev.amount < 0 else "dim")
        gold_color = "green" if ev.total_price > 0 else ("red" if ev.total_price < 0 else "dim")
        return (
            f"[dim]{time_label}[/dim]  {island}  {ev.display_partner}  "
            f"[{qty_color}]{ev.amount:+,}[/{qty_color}]  "
            f"[{gold_color}]{ev.total_price:+,}[/{gold_color}]"
        )
