"""trade.diff の単体テスト．"""

from __future__ import annotations

from anno_save_analyzer.trade import diff_by_item, diff_by_route
from anno_save_analyzer.trade.models import Item, TradeEvent, TradingPartner


def _ev(
    guid: int,
    amount: int,
    price: int,
    *,
    route_id: str | None = None,
    kind: str = "route",
) -> TradeEvent:
    return TradeEvent(
        item=Item(guid=guid, names={"en": f"Good_{guid}"}),
        amount=amount,
        total_price=price,
        partner=TradingPartner(id=route_id or "anon", display_name="x", kind=kind),
        route_id=route_id,
    )


class TestDiffByItem:
    def test_added_removed_changed_unchanged(self) -> None:
        before = [
            _ev(100, 3, 30),  # both
            _ev(200, 1, 10),  # only in before → removed
            _ev(300, 5, 50),  # both, unchanged
        ]
        after = [
            _ev(100, 5, 50),  # both, changed
            _ev(300, 5, 50),  # both, unchanged
            _ev(400, 2, 20),  # only in after → added
        ]
        result = {d.item.guid: d for d in diff_by_item(before, after)}
        assert result[100].status == "changed"
        assert result[100].bought_delta == 2
        assert result[100].net_gold_delta == 20
        assert result[200].status == "removed"
        assert result[200].bought_delta == -1
        assert result[300].status == "unchanged"
        assert result[300].bought_delta == 0
        assert result[400].status == "added"
        assert result[400].bought_delta == 2

    def test_sort_order_prefers_event_count_delta_desc(self) -> None:
        before = []
        after = [
            _ev(100, 1, 1),
            _ev(200, 1, 1),
            _ev(200, 1, 1),  # guid 200 has 2 events
            _ev(300, 1, 1),
        ]
        rows = diff_by_item(before, after)
        # guid=200 先頭 (count delta 2)，残り count=1 組は guid 昇順で 100, 300
        assert [d.item.guid for d in rows] == [200, 100, 300]

    def test_item_metadata_prefers_after_then_before(self) -> None:
        """after 側に item があればそちらの Item オブジェクトを採用．"""
        before = [_ev(100, 1, 1)]
        after = [_ev(100, 1, 1)]
        rows = diff_by_item(before, after)
        assert rows[0].item.guid == 100
        assert rows[0].display_name("en") == "Good_100"

    def test_item_metadata_falls_back_to_before_when_removed(self) -> None:
        """after に無い (removed) 場合は before 側の Item を使う．"""
        before = [_ev(100, 1, 1)]
        after = []
        rows = diff_by_item(before, after)
        assert rows[0].status == "removed"
        assert rows[0].item.guid == 100
        assert rows[0].display_name("en") == "Good_100"

    def test_empty_inputs_return_empty_list(self) -> None:
        assert diff_by_item([], []) == []


class TestDiffByRoute:
    def test_added_and_changed_routes(self) -> None:
        before = [_ev(100, 1, 10, route_id="A"), _ev(100, 1, 10, route_id="B")]
        after = [
            _ev(100, 3, 30, route_id="A"),  # changed
            _ev(100, 1, 10, route_id="C"),  # added
        ]
        result = {d.route_id: d for d in diff_by_route(before, after)}
        assert result["A"].status == "changed"
        assert result["A"].bought_delta == 2
        assert result["B"].status == "removed"
        assert result["C"].status == "added"

    def test_unchanged_route_detected(self) -> None:
        before = [_ev(100, 1, 10, route_id="X")]
        after = [_ev(100, 1, 10, route_id="X")]
        rows = diff_by_route(before, after)
        assert rows[0].status == "unchanged"
        assert rows[0].bought_delta == 0

    def test_sort_order_by_count_delta_then_route_id(self) -> None:
        before = []
        after = [
            _ev(1, 1, 1, route_id="A"),
            _ev(1, 1, 1, route_id="B"),
            _ev(1, 1, 1, route_id="B"),  # B has higher count
        ]
        rows = diff_by_route(before, after)
        assert rows[0].route_id == "B"
        assert rows[1].route_id == "A"

    def test_none_route_id_sorts_before_strings(self) -> None:
        before = []
        after = [
            _ev(1, 1, 1, route_id=None, kind="passive"),
            _ev(1, 1, 1, route_id="Z"),
        ]
        rows = diff_by_route(before, after)
        # 両方 count=1 なので route_id "" (None) が "Z" より先
        assert rows[0].route_id is None
        assert rows[1].route_id == "Z"

    def test_empty_returns_empty(self) -> None:
        assert diff_by_route([], []) == []
