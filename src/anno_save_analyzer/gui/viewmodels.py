"""GUI の view と model 層の間のアダプタ．

``TuiState`` / ``SupplyBalanceTable`` という純粋データから，Qt ウィジェットが
消費しやすい形 (表示 label 付き島リスト / 表示用行データ) に正規化する．
Qt に依存せず．ユニットテストで容易に検証できる．
"""

from __future__ import annotations

from dataclasses import dataclass

from anno_save_analyzer.trade.balance import ProductBalance, SupplyBalanceTable
from anno_save_analyzer.trade.items import ItemDictionary

_NPC_PREFIX = "(NPC) "


@dataclass(frozen=True)
class IslandListItem:
    """左ペインの SelectionList 1 行分．"""

    area_manager: str
    display_label: str
    is_player: bool
    resident_total: int


@dataclass(frozen=True)
class BalanceRow:
    """中央テーブル 1 行分．produced / consumed / delta を文字列化済み．"""

    product_guid: int
    product_name: str
    produced_text: str
    consumed_text: str
    delta_text: str
    is_deficit: bool
    delta_value: float


def make_island_items(
    table: SupplyBalanceTable,
    *,
    area_manager_to_city: dict[str, str] | None = None,
    area_manager_to_session: dict[str, str] | None = None,
) -> list[IslandListItem]:
    """左ペイン用に島リストを組み立てる．プレイヤー → NPC の順にソート．

    ``area_manager_to_city`` は Jaccard match 成功 AM の city 名．match 失敗は
    NPC 扱い．``area_manager_to_session`` は session 表示名 (Localizer 解決後)．
    """
    city_map = area_manager_to_city or {}
    sess_map = area_manager_to_session or {}
    items: list[IslandListItem] = []
    for isl in table.islands:
        city = city_map.get(isl.area_manager) or isl.city_name
        session = sess_map.get(isl.area_manager, "")
        is_player = bool(city)
        name = city or isl.area_manager
        prefix = "" if is_player else _NPC_PREFIX
        session_suffix = f"  [{session}]" if session else ""
        label = f"{prefix}{name}{session_suffix}  ({isl.resident_total:,} pop)"
        items.append(
            IslandListItem(
                area_manager=isl.area_manager,
                display_label=label,
                is_player=is_player,
                resident_total=isl.resident_total,
            )
        )
    # player_first: True(=player) を先に (Python の False < True なので reverse)
    items.sort(key=lambda x: (not x.is_player, -x.resident_total))
    return items


def make_balance_rows(
    products: tuple[ProductBalance, ...],
    items: ItemDictionary,
    locale: str = "en",
) -> list[BalanceRow]:
    """物資 balance を表示文字列付きの行データにする．deficit → worst first．"""
    rows: list[BalanceRow] = []
    for p in sorted(products, key=lambda q: q.delta_per_minute):
        item = items[p.product_guid]
        name = item.display_name(locale) or f"Good_{p.product_guid}"
        rows.append(
            BalanceRow(
                product_guid=p.product_guid,
                product_name=name,
                produced_text=f"{p.produced_per_minute:.2f}",
                consumed_text=f"{p.consumed_per_minute:.2f}",
                delta_text=f"{p.delta_per_minute:+.2f}",
                is_deficit=p.is_deficit,
                delta_value=p.delta_per_minute,
            )
        )
    return rows
