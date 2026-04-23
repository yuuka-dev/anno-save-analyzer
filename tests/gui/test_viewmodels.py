"""``gui.viewmodels`` は Qt 非依存なので通常 unit test．

``pytest -m gui`` で走る (pyproject の default addopts で除外されているため)．
"""

from __future__ import annotations

import pytest

from anno_save_analyzer.gui.viewmodels import (
    BalanceRow,
    IslandListItem,
    make_balance_rows,
    make_island_items,
)
from anno_save_analyzer.trade.balance import (
    IslandBalance,
    ProductBalance,
    SupplyBalanceTable,
)
from anno_save_analyzer.trade.items import ItemDictionary
from anno_save_analyzer.trade.models import Item

pytestmark = pytest.mark.gui


def _items_dict(**names: dict[str, str]) -> ItemDictionary:
    entries = {int(k): Item(guid=int(k), names=v) for k, v in names.items() if isinstance(v, dict)}
    return ItemDictionary(entries)


def test_make_island_items_sorts_player_first() -> None:
    table = SupplyBalanceTable(
        islands=(
            IslandBalance(area_manager="AM_NPC", city_name=None, resident_total=800, products=()),
            IslandBalance(area_manager="AM_P1", city_name="岡山", resident_total=1000, products=()),
            IslandBalance(area_manager="AM_P2", city_name="広島", resident_total=500, products=()),
        )
    )
    items = make_island_items(table)
    # プレイヤー島先．プレイヤー内は人口多い順
    assert [it.area_manager for it in items] == ["AM_P1", "AM_P2", "AM_NPC"]
    assert [it.is_player for it in items] == [True, True, False]


def test_make_island_items_applies_city_map() -> None:
    """area_manager_to_city が与えられれば city_name より優先．"""
    table = SupplyBalanceTable(
        islands=(
            IslandBalance(area_manager="AM_1", city_name=None, resident_total=100, products=()),
        )
    )
    items = make_island_items(
        table,
        area_manager_to_city={"AM_1": "別名島"},
        area_manager_to_session={"AM_1": "トレローニー岬"},
    )
    assert items[0].is_player is True
    assert "別名島" in items[0].display_label
    assert "トレローニー岬" in items[0].display_label


def test_make_island_items_npc_prefix() -> None:
    table = SupplyBalanceTable(
        islands=(
            IslandBalance(area_manager="AM_NPC_1", city_name=None, resident_total=200, products=()),
        )
    )
    items = make_island_items(table)
    assert items[0].is_player is False
    assert items[0].display_label.startswith("(NPC) AM_NPC_1")


def test_make_balance_rows_sorted_by_worst_delta() -> None:
    items = _items_dict(**{"200": {"en": "Fish"}, "300": {"en": "Rum"}})  # type: ignore[arg-type]
    products = (
        ProductBalance(product_guid=200, produced_per_minute=5, consumed_per_minute=2),  # +3
        ProductBalance(product_guid=300, produced_per_minute=1, consumed_per_minute=4),  # -3
    )
    rows = make_balance_rows(products, items, locale="en")
    assert [r.product_guid for r in rows] == [300, 200]
    assert rows[0].is_deficit is True
    assert rows[0].delta_text == "-3.00"
    assert rows[1].is_deficit is False
    assert rows[1].delta_text == "+3.00"


def test_make_balance_rows_falls_back_to_good_prefix_for_unknown() -> None:
    items = ItemDictionary({})
    rows = make_balance_rows(
        (ProductBalance(product_guid=999, produced_per_minute=0, consumed_per_minute=1),),
        items,
        locale="en",
    )
    assert rows[0].product_name == "Good_999"


def test_dataclass_frozen() -> None:
    it = IslandListItem(area_manager="A", display_label="L", is_player=True, resident_total=1)
    with pytest.raises(Exception):  # noqa: B017
        it.is_player = False  # type: ignore[misc]
    row = BalanceRow(
        product_guid=1,
        product_name="x",
        produced_text="",
        consumed_text="",
        delta_text="",
        is_deficit=False,
        delta_value=0,
    )
    with pytest.raises(Exception):  # noqa: B017
        row.product_name = "y"  # type: ignore[misc]
