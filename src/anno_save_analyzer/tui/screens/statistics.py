"""Trade Statistics 画面．3 カラム: Tree / DataTable / Partners pane．"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
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

from anno_save_analyzer.trade.aggregate import ItemSummary, RouteSummary

from ..i18n import Localizer
from ..state import TuiState


class TradeStatisticsScreen(Screen):
    """3 カラム統計画面．"""

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
    TradeStatisticsScreen #partners-pane {
        width: 36;
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
            yield Static(
                f"[b]{t('partners.heading')}[/b]\n\n{t('partners.placeholder')}",
                id="partners-pane",
            )
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
        t = self._localizer.t
        table.add_columns(
            t("statistics.col.good"),
            t("statistics.col.bought"),
            t("statistics.col.sold"),
            t("statistics.col.net_qty"),
            t("statistics.col.net_gold"),
            t("statistics.col.events"),
        )
        for s in self._state.item_summaries:
            table.add_row(*self._format_item_row(s))
        return table

    def _render_routes_table(self) -> DataTable:
        table = DataTable(id="routes-table")
        t = self._localizer.t
        table.add_columns(
            t("statistics.col.route"),
            t("statistics.col.kind"),
            t("statistics.col.bought"),
            t("statistics.col.sold"),
            t("statistics.col.net_gold"),
            t("statistics.col.events"),
        )
        for s in self._state.route_summaries:
            table.add_row(*self._format_route_row(s))
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

    def _format_route_row(self, s: RouteSummary) -> tuple[str, ...]:
        route_id = s.route_id if s.route_id is not None else "—"
        return (
            route_id,
            s.partner_kind,
            f"{s.bought:,}",
            f"{s.sold:,}",
            f"{s.net_gold:+,}",
            f"{s.event_count:,}",
        )
