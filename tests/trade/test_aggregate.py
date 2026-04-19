"""trade.aggregate のテスト．"""

from __future__ import annotations

from anno_save_analyzer.trade.aggregate import by_item, by_route
from anno_save_analyzer.trade.models import Item, TradeEvent, TradingPartner


def _ev(
    guid: int,
    amount: int,
    price: int,
    *,
    route_id: str | None = None,
    kind: str = "unknown",
    timestamp: int | None = None,
    partner: TradingPartner | None | object = ...,
) -> TradeEvent:
    item = Item(guid=guid, names={"en": f"Good_{guid}"})
    # partner = sentinel (...) なら kind と route_id から自動生成．
    # partner = None を明示的に指定した時のみ partner を持たせない．
    if partner is ...:
        partner = TradingPartner(id=route_id or "anon", display_name="x", kind=kind)
    return TradeEvent(
        item=item,
        amount=amount,
        total_price=price,
        partner=partner,
        route_id=route_id,
        timestamp_tick=timestamp,
    )


class TestByItem:
    def test_aggregates_buys_sells_and_net(self) -> None:
        events = [
            _ev(1, 10, -100),
            _ev(1, -3, 30),
            _ev(2, 5, -50),
        ]
        rows = by_item(events)
        guids = [r.item.guid for r in rows]
        assert guids == [1, 2]
        r1 = next(r for r in rows if r.item.guid == 1)
        assert r1.bought == 10
        assert r1.sold == 3
        assert r1.net_qty == 7
        assert r1.net_gold == -70
        assert r1.event_count == 2

    def test_last_seen_tracks_max_timestamp(self) -> None:
        events = [
            _ev(1, 1, 1, timestamp=100),
            _ev(1, 1, 1, timestamp=300),
            _ev(1, 1, 1, timestamp=200),
            _ev(1, 1, 1, timestamp=None),
        ]
        rows = by_item(events)
        assert rows[0].last_seen_tick == 300

    def test_zero_amount_does_not_count_toward_buys_or_sells(self) -> None:
        events = [_ev(1, 0, 0)]
        rows = by_item(events)
        assert rows[0].bought == 0
        assert rows[0].sold == 0

    def test_sort_order_is_stable_by_count_then_guid(self) -> None:
        events = [
            _ev(2, 1, 1),
            _ev(2, 1, 1),
            _ev(2, 1, 1),
            _ev(1, 1, 1),
            _ev(1, 1, 1),
            _ev(3, 1, 1),
            _ev(3, 1, 1),
        ]
        rows = by_item(events)
        guids = [r.item.guid for r in rows]
        # 2 (count=3), then 1 / 3 are tied at count=2 → guid 昇順 → 1, 3
        assert guids == [2, 1, 3]

    def test_display_name_helper(self) -> None:
        events = [_ev(2088, 1, 1)]
        rows = by_item(events)
        assert rows[0].display_name("en") == "Good_2088"


class TestByRoute:
    def test_groups_by_route_id_and_kind(self) -> None:
        events = [
            _ev(1, 5, -10, route_id="r1", kind="route"),
            _ev(2, -2, 4, route_id="r1", kind="route"),
            _ev(3, 1, 1, route_id=None, kind="passive"),
        ]
        rows = by_route(events)
        keys = [(r.route_id, r.partner_kind) for r in rows]
        assert ("r1", "route") in keys
        assert (None, "passive") in keys

    def test_unknown_partner_kind_when_partner_none(self) -> None:
        item = Item(guid=1, names={})
        events = [TradeEvent(item=item, amount=1, total_price=1)]
        rows = by_route(events)
        assert rows[0].partner_kind == "unknown"

    def test_zero_amount_does_not_increment_buy_sell(self) -> None:
        events = [_ev(1, 0, 0, route_id="r1", kind="route")]
        rows = by_route(events)
        assert rows[0].bought == 0
        assert rows[0].sold == 0

    def test_last_seen_tracks_max_per_route(self) -> None:
        events = [
            _ev(1, 1, 1, route_id="r1", kind="route", timestamp=100),
            _ev(1, 1, 1, route_id="r1", kind="route", timestamp=500),
            _ev(1, 1, 1, route_id="r1", kind="route", timestamp=300),
        ]
        rows = by_route(events)
        assert rows[0].last_seen_tick == 500

    def test_sort_by_event_count_then_route_id(self) -> None:
        events = [
            _ev(1, 1, 1, route_id="r2", kind="route"),
            _ev(1, 1, 1, route_id="r2", kind="route"),
            _ev(1, 1, 1, route_id="r1", kind="route"),
        ]
        rows = by_route(events)
        # r2 が count=2 で先頭，r1 が count=1
        assert rows[0].route_id == "r2"
        assert rows[1].route_id == "r1"
