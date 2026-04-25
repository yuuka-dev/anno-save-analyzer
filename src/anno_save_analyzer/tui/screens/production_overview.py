"""Production Overview 画面．3 カラム: Tree / DataTable / Detail+sparkline．

Issue #98 で書記長 (現プレイヤー) が要望．「TUI に生産設備のリストと稼働率
表示する機能がほしい」．

レイアウト:

- **左 Tree**: All islands (root) > session > island の階層．Anno 1800 のみ
  実値が乗る (factories_by_island は load_state で AreaManager から組む)．
- **中央 DataTable**: 1 行 = 1 工場種類 (building_guid 単位の集計)．列:
  工場名 / 数 / 平均 productivity (%) / 出力物資 / 生産レート (t/min) /
  入力物資．入力物資列は ``inputs`` を recipe から取って物資名を ``,`` 連結．
- **右 Detail pane**: 選択行の summary + 個別 productivity sparkline．

依存:

- :class:`FactoryRecipeTable` で building_guid → recipe を引き，出力物資 /
  入力物資 / tpmin を取得．未登録 building は recipe-less で行ごと省略．
- :class:`ItemDictionary` で物資名を locale 解決．

非スコープ (将来拡張): 工場の建設提案 (Decision Matrix / #96)，
時系列 productivity (StorageTrends は物資単位なので工場単位の履歴は無い)．
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Static,
    Tree,
)

from anno_save_analyzer.trade.factories import FactoryInstance
from anno_save_analyzer.trade.factory_recipes import FactoryRecipe, FactoryRecipeTable

from ..i18n import Localizer
from ..sparkline import sparkline
from ..state import TuiState


class ProductionOverviewScreen(Screen):
    """工場一覧と稼働率を島単位で表示する画面．"""

    DEFAULT_CSS = """
    ProductionOverviewScreen Horizontal {
        height: 1fr;
    }
    ProductionOverviewScreen Tree {
        width: 28;
        border: solid $primary;
        border-title-color: $accent;
    }
    ProductionOverviewScreen #production-table-pane {
        width: 1fr;
        border: solid $primary;
        border-title-color: $accent;
        padding: 0 1;
    }
    ProductionOverviewScreen #production-summary {
        height: auto;
        padding: 0 0 1 0;
        color: $text-muted;
    }
    ProductionOverviewScreen #production-table {
        height: 1fr;
    }
    ProductionOverviewScreen #production-detail-pane {
        width: 36;
        border: solid $primary;
        border-title-color: $accent;
        padding: 0 1;
    }
    """

    # Tree node の data に持たせる selector．None = root．
    # str はそのまま「session_id (sid)」または「island_key」を表す．
    # 見分けは set 帰属 (session_ids / factories_by_island) で行う．
    BINDINGS: list[Binding] = []

    def __init__(self, state: TuiState, localizer: Localizer) -> None:
        super().__init__(name="production_overview")
        self._state = state
        self._localizer = localizer
        # 現在 Tree で選択中の filter．None = All．それ以外は (kind, value)．
        self._filter: tuple[str, str] | None = None
        # FactoryRecipeTable を 1 度だけ load (失敗時 None)．Anno 1800 以外は
        # データが無いので空テーブル相当で表示するフォールバック．
        self._recipes: FactoryRecipeTable | None = self._try_load_recipes()
        # building_guid → recipe を直接引けるように cache．
        self._recipe_by_guid: dict[int, FactoryRecipe] = (
            dict(self._recipes.recipes) if self._recipes is not None else {}
        )
        # 最後に detail pane に表示した row の (island_key, building_guid)．
        self._last_detail_row: tuple[str, int] | None = None

    @staticmethod
    def _try_load_recipes() -> FactoryRecipeTable | None:
        try:
            return FactoryRecipeTable.load()
        except (FileNotFoundError, ValueError):  # pragma: no cover - defensive
            return None

    def set_localizer(self, localizer: Localizer) -> None:
        """``TradeApp.switch_locale`` から呼ばれる公開 setter．"""
        self._localizer = localizer

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal():
            yield self._build_tree()
            yield Vertical(
                Static("", id="production-summary"),
                self._build_table(),
                id="production-table-pane",
            )
            yield Vertical(
                Static("", id="production-detail"),
                id="production-detail-pane",
            )
        yield Footer()

    def on_mount(self) -> None:
        # ``border_title`` / Static の初期値は compose 中 ``query_one`` できない
        # ので ここでまとめて設定．DataTable の列と行は ``_build_table``
        # (compose 経由) で済んでる．recompose 後は ``Screen.on_mount`` が再
        # 呼ばれない仕様だが，compose 内で全列 + 初期行を確定させてるので
        # 表示破壊は起きない．切替後の border_title 更新は ``set_localizer``
        # から ``refresh(recompose=True)`` で行う流れで吸収する．
        self._apply_border_titles()
        # 初期 summary / detail 文言．
        summary = self.query_one("#production-summary", Static)
        # ``compose`` 経由で table は埋まっているので，再度 islands を計算するのみ．
        islands = self._selected_islands()
        # 集計だけ取り直す (table から逆算してもよいが純粋関数で再計算が素直)．
        total_factories = sum(
            len(self._state.factories_by_island[k].instances)
            for k in islands
            if k in self._state.factories_by_island
        )
        # 総レートは row 数に依存しないので 0 で OK (All タブ初期はサマリだけ)．
        summary.update(self._format_summary(islands, total_factories, 0.0))
        self._set_detail(self._loc("production.detail.empty"))

    def _apply_border_titles(self) -> None:
        tree = self.query_one(Tree)
        tree.border_title = self._loc("production.tree.title")
        pane = self.query_one("#production-table-pane")
        pane.border_title = self._loc("production.table.title")
        detail_pane = self.query_one("#production-detail-pane")
        detail_pane.border_title = self._loc("production.detail.title")

    # ---------- Events ----------

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if data is None:
            self._filter = None
        elif isinstance(data, tuple) and len(data) == 2:
            self._filter = data
        else:  # pragma: no cover - defensive
            self._filter = None
        self._refresh_table()
        self._set_detail(self._loc("production.detail.empty"))
        self._last_detail_row = None

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        row_key = event.row_key.value if event.row_key is not None else None
        if row_key is None:
            return
        # row_key = "<island_key>::<building_guid>" 形式．
        try:
            island_key, guid_str = row_key.split("::", 1)
            building_guid = int(guid_str)
        except ValueError:  # pragma: no cover - defensive
            return
        self._last_detail_row = (island_key, building_guid)
        self._update_detail_pane(island_key, building_guid)

    # ---------- Helpers ----------

    def _loc(self, key: str, **kwargs: object) -> str:
        return self._localizer.t(key, **kwargs)

    def _build_table(self) -> DataTable:
        """DataTable を組み立てて初期行も埋める．``compose`` から直接 yield する．

        ``on_mount`` で columns を追加していると locale 切替 (recompose) 後に
        on_mount が再呼ばれず空テーブル化してしまう．compose 内で columns を
        確定させ，行も同時に埋めることで recompose 経由で常に同期する．
        """
        table = DataTable(id="production-table", cursor_type="row", zebra_stripes=True)
        table.add_columns(
            self._loc("production.col.factory"),
            self._loc("production.col.count"),
            self._loc("production.col.productivity"),
            self._loc("production.col.output"),
            self._loc("production.col.rate"),
            self._loc("production.col.input"),
        )
        # 行は ``_populate_table_rows`` で埋める．summary も同時に更新するが，
        # ``compose`` 中はまだ ``query_one`` で Static が取れないので detail /
        # summary 文字列は (compose 完了後の) ``on_mount`` でセットする．
        self._populate_table_rows(table)
        return table

    def _build_tree(self) -> Tree:
        """session > island の Tree．data には ``("session", sid)`` か
        ``("island", island_key)`` を入れる．root は data=None．
        """
        tree = Tree[tuple[str, str] | None](self._loc("production.tree.root"), id="production-tree")
        tree.root.data = None
        tree.root.expand()
        keys = self._state.session_locale_keys or tuple(
            "session.unknown" for _ in self._state.session_ids
        )
        islands_by_sid = self._state.islands_by_session
        am_to_city = self._state.area_manager_to_city
        # NPC / 未マッチ島も factories_by_island に乗ってるので tree に出す．
        used_island_keys: set[str] = set()
        for sid, lkey in zip(self._state.session_ids, keys, strict=False):
            session_label = self._loc("production.tree.session", name=self._loc(lkey, index=sid))
            session_node = tree.root.add(session_label, expand=True, data=("session", sid))
            for isl in islands_by_sid.get(sid, ()):
                key = isl.city_name
                if key in self._state.factories_by_island:
                    session_node.add_leaf(
                        self._loc("production.tree.island", name=key),
                        data=("island", key),
                    )
                    used_island_keys.add(key)
            # NPC / 未マッチ島: AreaManager_N を直接 leaf に．session が紐付けら
            # れないため "Other" バケツ的な扱い．session に従属させない．
        npc_keys = sorted(set(self._state.factories_by_island) - used_island_keys - set(am_to_city))
        for key in npc_keys:
            tree.root.add_leaf(
                self._loc("production.tree.island", name=key),
                data=("island", key),
            )
        return tree

    def _selected_islands(self) -> list[str]:
        """現在の filter に該当する island_key 一覧を返す．"""
        all_keys = list(self._state.factories_by_island)
        if self._filter is None:
            return sorted(all_keys)
        kind, value = self._filter
        if kind == "island":
            return [value] if value in self._state.factories_by_island else []
        if kind == "session":
            islands = self._state.islands_by_session.get(value, ())
            return [
                isl.city_name for isl in islands if isl.city_name in self._state.factories_by_island
            ]
        return sorted(all_keys)

    def _populate_table_rows(self, table: DataTable) -> tuple[int, float, list[str]]:
        """``table`` に現フィルタの行を流し込み，``(工場数, 総レート, 島リスト)`` を返す．

        ``compose`` 経由 (新規 table) と event handler 経由 (既存 table) の
        両方から呼べるよう，table 引数を受け取る．返り値は summary 描画用．
        """
        table.clear()
        islands = self._selected_islands()
        total_factories = 0
        total_rate = 0.0
        for key in islands:
            agg = self._state.factories_by_island.get(key)
            if agg is None:
                continue
            grouped = agg.by_building()
            for guid in sorted(grouped):
                instances = grouped[guid]
                recipe = self._recipe_by_guid.get(guid)
                factory_name = (
                    recipe.name if recipe is not None and recipe.name else f"Building_{guid}"
                )
                count = len(instances)
                mean_prod = sum(i.productivity for i in instances) / count if count else 0.0
                output_text, rate, input_text = self._format_recipe_columns(recipe, instances)
                total_factories += count
                total_rate += rate
                row_key = f"{key}::{guid}"
                table.add_row(
                    factory_name,
                    f"{count:,}",
                    f"{mean_prod * 100:.0f}",
                    output_text,
                    f"{rate:.2f}",
                    input_text,
                    key=row_key,
                )
        return total_factories, total_rate, islands

    def _refresh_table(self) -> None:
        table = self.query_one(DataTable)
        total_factories, total_rate, islands = self._populate_table_rows(table)
        summary = self.query_one("#production-summary", Static)
        summary.update(self._format_summary(islands, total_factories, total_rate))

    def _format_recipe_columns(
        self,
        recipe: FactoryRecipe | None,
        instances: tuple[FactoryInstance, ...],
    ) -> tuple[str, float, str]:
        """``(出力物資, 生産レート t/min, 入力物資)`` を求める．

        生産レート = Σ_instance productivity × tpmin × output.amount．未登録
        recipe / tpmin 欠の場合 0．
        TODO(#96): 入力物資の消費レートが balance pipeline で算出可能になった
        ら，その値もここで列に反映する (現状は名前のみ)．
        """
        if recipe is None:
            return ("—", 0.0, "")
        # 出力物資名 (locale 解決)
        output_names: list[str] = []
        rate = 0.0
        primary_amount = 1.0
        for output in recipe.outputs:
            item = self._state.items[output.product_guid]
            output_names.append(item.display_name(self._localizer.code))
            if output is recipe.outputs[0]:
                primary_amount = output.amount if output.amount is not None else 1.0
        if recipe.tpmin is not None:
            for inst in instances:
                rate += inst.productivity * recipe.tpmin * primary_amount
        # 入力物資名 (#96 後に消費レートも併記したい．現状は名前のみ)．
        input_names: list[str] = []
        for inp in recipe.inputs:
            item = self._state.items[inp.product_guid]
            input_names.append(item.display_name(self._localizer.code))
        output_text = ", ".join(output_names) if output_names else "—"
        input_text = ", ".join(input_names)
        return (output_text, rate, input_text)

    def _format_summary(self, islands: list[str], factories: int, rate: float) -> str:
        if not islands:
            return self._loc("production.summary.empty")
        if self._filter is None:
            return self._loc(
                "production.summary.all",
                islands=len(islands),
                factories=factories,
            )
        kind, value = self._filter
        if kind == "island":
            return self._loc(
                "production.summary.island",
                name=value,
                factories=factories,
                rate=rate,
            )
        # session
        keys = self._state.session_locale_keys or tuple(
            "session.unknown" for _ in self._state.session_ids
        )
        # session id → locale key 解決．
        locale_key = next(
            (k for s, k in zip(self._state.session_ids, keys, strict=False) if s == value),
            "session.unknown",
        )
        session_label = self._loc(locale_key, index=value)
        return self._loc(
            "production.summary.session",
            name=session_label,
            islands=len(islands),
            factories=factories,
        )

    def _set_detail(self, body: str) -> None:
        self.query_one("#production-detail", Static).update(body)

    def _update_detail_pane(self, island_key: str, building_guid: int) -> None:
        """選択行に対応する factory instances の productivity 履歴を表示．

        save から取れる工場時系列は無いため，「個々の instance の現
        productivity 値」を sparkline 化する．100 個の Lumberjack hut が並ぶ
        ような状況で，どの個体が低稼働かをパッと掴めるようにする．
        """
        agg = self._state.factories_by_island.get(island_key)
        if agg is None:
            return
        grouped = agg.by_building()
        instances = grouped.get(building_guid)
        if not instances:
            return
        recipe = self._recipe_by_guid.get(building_guid)
        factory_name = (
            recipe.name if recipe is not None and recipe.name else f"Building_{building_guid}"
        )
        productivities = [inst.productivity for inst in instances]
        mean_prod = sum(productivities) / len(productivities)
        output_text, rate, _ = self._format_recipe_columns(recipe, instances)
        sparkline_text = sparkline(productivities, width=24)
        body = self._loc(
            "production.detail.line",
            factory=factory_name,
            count=len(instances),
            productivity=f"{mean_prod * 100:.0f}%",
            rate=rate,
            output=output_text,
        )
        body += (
            "\n[dim]" + self._loc("production.detail.sparkline_label") + "[/dim] " + sparkline_text
        )
        self._set_detail(body)
