"""Supply Balance 画面．島 multi-select + 物資別 balance DataTable．

3 カラム設計 (#68 issue) のうち，MVP として左 SelectionList / 中央 DataTable
のみ実装．右ペイン (product detail) は将来拡張．

書記長の用途: Anno 1800 プレイ中に save を読み込んで「どの島でどの物資が
赤字か」を即座に比較する．SelectionList で島を複数チェック → aggregate
結果が中央テーブルに反映される．
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    SelectionList,
    Static,
)

from anno_save_analyzer.trade.balance import IslandBalance

from ..i18n import Localizer
from ..state import TuiState


class SupplyBalanceScreen(Screen):
    """島 × 物資の supply balance を表示する画面．"""

    DEFAULT_CSS = """
    SupplyBalanceScreen Horizontal {
        height: 1fr;
    }
    SupplyBalanceScreen SelectionList {
        width: 35%;
        border: solid $primary;
        border-title-color: $accent;
    }
    SupplyBalanceScreen #balance-pane {
        width: 65%;
        border: solid $primary;
        border-title-color: $accent;
        padding: 0 1;
    }
    SupplyBalanceScreen #balance-summary {
        height: auto;
        padding: 0 0 1 0;
        color: $text-muted;
    }
    SupplyBalanceScreen #balance-table {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("d", "toggle_deficit_only", "Deficit only", show=True),
        Binding("b", "toggle_bonus_needs", "Bonus needs", show=True),
        Binding("a", "select_all", "Select all", show=True),
        Binding("n", "select_none", "Clear", show=True),
    ]

    deficit_only: reactive[bool] = reactive(False)

    def __init__(self, state: TuiState, localizer: Localizer) -> None:
        super().__init__()
        self._state = state
        self._localizer = localizer

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal():
            yield SelectionList[str](
                *self._selection_options(),
                id="island-selection",
            )
            from textual.containers import Vertical

            pane = Vertical(
                Static("", id="balance-summary"),
                DataTable(id="balance-table", cursor_type="row", zebra_stripes=True),
                id="balance-pane",
            )
            yield pane
        yield Footer()

    def on_mount(self) -> None:
        # SelectionList border title
        sel = self.query_one(SelectionList)
        sel.border_title = self._loc("balance.islands.title")
        pane = self.query_one("#balance-pane")
        pane.border_title = self._loc("balance.table.title")

        # DataTable カラム．
        table = self.query_one(DataTable)
        table.add_columns(
            self._loc("balance.col.product"),
            self._loc("balance.col.produced"),
            self._loc("balance.col.consumed"),
            self._loc("balance.col.delta"),
        )
        # 初期は全島 select
        sel.select_all()

    # ---------- Events ----------

    def on_selection_list_selected_changed(self, event: SelectionList.SelectedChanged) -> None:
        self._refresh_table()

    def action_toggle_deficit_only(self) -> None:
        self.deficit_only = not self.deficit_only
        self._refresh_table()

    def action_toggle_bonus_needs(self) -> None:
        """bonus needs toggle は MVP では再計算 pipeline 無しなので未対応．
        hook だけ残して将来の拡張点にする．
        """
        self.notify(
            self._loc("balance.bonus_toggle.todo"),
            severity="warning",
            timeout=2.0,
        )

    def action_select_all(self) -> None:
        self.query_one(SelectionList).select_all()

    def action_select_none(self) -> None:
        self.query_one(SelectionList).deselect_all()

    # ---------- Helpers ----------

    def _loc(self, key: str) -> str:
        return self._localizer.t(key)

    def _selection_options(self) -> list[tuple[str, str]]:
        """``(label, value)`` のペアを返す．value=area_manager．"""
        table = self._state.balance_table
        if table is None:
            return []
        rows: list[tuple[str, str]] = []
        for isl in table.islands:
            label = isl.city_name or isl.area_manager
            rows.append((self._format_island_label(isl, label), isl.area_manager))
        return rows

    @staticmethod
    def _format_island_label(isl: IslandBalance, display: str) -> str:
        return f"{display}  ({isl.resident_total:,} pop)"

    def _refresh_table(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        source = self._state.balance_table
        if source is None:
            return
        selected_ams = set(self.query_one(SelectionList).selected)
        combined = source.aggregate(selected_ams) if selected_ams else source.aggregate(())
        products = combined.deficits() if self.deficit_only else combined.products
        for p in sorted(products, key=lambda q: q.delta_per_minute):
            item = self._state.items[p.product_guid]
            name = item.display_name(self._state.locale) or f"Good_{p.product_guid}"
            prod_text = f"{p.produced_per_minute:.2f}"
            cons_text = f"{p.consumed_per_minute:.2f}"
            delta_style = (
                "red" if p.is_deficit else ("green" if p.delta_per_minute > 0 else "white")
            )
            delta_text = Text(f"{p.delta_per_minute:+.2f}", style=delta_style)
            table.add_row(name, prod_text, cons_text, delta_text)

        summary = self.query_one("#balance-summary", Static)
        if not selected_ams:
            summary.update(self._loc("balance.summary.none"))
        else:
            summary.update(
                self._loc("balance.summary").format(
                    islands=len(selected_ams),
                    population=f"{combined.resident_total:,}",
                    products=len(products),
                )
            )
