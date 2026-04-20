"""trade.models のテスト．"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from anno_save_analyzer.trade.models import (
    GameTitle,
    Item,
    TradeEvent,
    TradingPartner,
)


class TestItem:
    def test_display_name_resolves_locale(self) -> None:
        item = Item(guid=2088, names={"en": "Wood", "ja": "木材"}, category="raw")
        assert item.display_name("en") == "Wood"
        assert item.display_name("ja") == "木材"

    def test_display_name_falls_back_to_en(self) -> None:
        item = Item(guid=2088, names={"en": "Wood"}, category="raw")
        assert item.display_name("fr") == "Wood"

    def test_display_name_falls_back_to_good_marker(self) -> None:
        item = Item(guid=9999, names={})
        assert item.display_name("en") == "Good_9999"
        assert item.display_name("ja") == "Good_9999"

    def test_empty_string_names_are_stripped(self) -> None:
        item = Item(guid=2088, names={"en": "Wood", "ja": ""})
        assert item.display_name("ja") == "Wood"

    def test_item_is_frozen(self) -> None:
        item = Item(guid=1, names={"en": "X"})
        with pytest.raises(ValidationError):
            item.guid = 2  # type: ignore[misc]


class TestTradeEvent:
    def test_buy_sell_flags(self) -> None:
        item = Item(guid=1, names={"en": "X"})
        buy = TradeEvent(item=item, amount=5, total_price=-100)
        sell = TradeEvent(item=item, amount=-3, total_price=60)
        zero = TradeEvent(item=item, amount=0, total_price=0)
        assert buy.is_buy and not buy.is_sell
        assert sell.is_sell and not sell.is_buy
        assert not zero.is_buy and not zero.is_sell

    def test_optional_fields_default_to_none(self) -> None:
        item = Item(guid=1, names={"en": "X"})
        ev = TradeEvent(item=item, amount=1, total_price=1)
        assert ev.partner is None
        assert ev.route_id is None
        assert ev.session_id is None
        assert ev.timestamp_tick is None
        assert ev.source_method == "history"


class TestTradingPartner:
    def test_construction(self) -> None:
        p = TradingPartner(id="42", display_name="Tobias", kind="passive")
        assert p.id == "42"
        assert p.kind == "passive"


class TestGameTitle:
    def test_values_have_no_underscore(self) -> None:
        # YAML ファイル名と整合させるためアンダースコア無しで揃える．
        assert GameTitle.ANNO_117.value == "anno117"
        assert GameTitle.ANNO_1800.value == "anno1800"
