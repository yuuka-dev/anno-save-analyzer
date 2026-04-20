"""trade.aggregate のテスト．"""

from __future__ import annotations

from anno_save_analyzer.trade.aggregate import (
    by_item,
    by_route,
    filter_events,
    partners_for_item,
)
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
    session_id: str | None = None,
    island_name: str | None = None,
    route_name: str | None = None,
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
        session_id=session_id,
        island_name=island_name,
        route_name=route_name,
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

    def test_route_name_aggregates_with_latest_tick_winning(self) -> None:
        """同一 route_id 内で途中 rename された場合，tick が進むタイミングで上書き．"""
        events = [
            _ev(1, 1, 1, route_id="7", kind="route", timestamp=100, route_name="旧ルート"),
            _ev(1, 1, 1, route_id="7", kind="route", timestamp=200, route_name="新ルート"),
        ]
        rows = by_route(events)
        assert rows[0].route_name == "新ルート"
        assert rows[0].display_route == "新ルート"

    def test_route_name_latest_tick_wins_even_if_events_are_out_of_order(self) -> None:
        events = [
            _ev(1, 1, 1, route_id="7", kind="route", timestamp=200, route_name="新ルート"),
            _ev(1, 1, 1, route_id="7", kind="route", timestamp=100, route_name="旧ルート"),
        ]
        rows = by_route(events)
        assert rows[0].route_name == "新ルート"

    def test_display_route_fallback_chain(self) -> None:
        """route_name > ``#{route_id}`` > ``—``."""
        events = [
            _ev(1, 1, 1, route_id="42", kind="route"),
            _ev(2, 1, 1, route_id=None, kind="unknown", partner=None),
        ]
        rows = by_route(events)
        labels = {r.display_route for r in rows}
        assert "#42" in labels
        assert "—" in labels


class TestPartnersForItem:
    def test_groups_by_route_and_partner_kind(self) -> None:
        events = [
            _ev(100, 3, 30, route_id="42", kind="route"),
            _ev(100, -1, -10, route_id="42", kind="route"),
            _ev(100, 5, 50, route_id="66", kind="route"),
            _ev(200, 7, 70, route_id="42", kind="route"),  # 別 item → 無視
        ]
        rows = partners_for_item(events, 100)
        assert {r.route_id for r in rows} == {"42", "66"}
        r42 = next(r for r in rows if r.route_id == "42")
        assert r42.bought == 3
        assert r42.sold == 1
        assert r42.net_gold == 20
        assert r42.event_count == 2

    def test_returns_empty_when_guid_absent(self) -> None:
        events = [_ev(100, 1, 10, route_id="x")]
        assert partners_for_item(events, 999) == []

    def test_zero_amount_does_not_count_toward_buy_or_sell(self) -> None:
        events = [_ev(100, 0, 0, route_id="r")]
        rows = partners_for_item(events, 100)
        assert rows[0].bought == 0 and rows[0].sold == 0
        assert rows[0].event_count == 1

    def test_sort_by_event_count_then_abs_gold(self) -> None:
        events = [
            _ev(100, 1, 10, route_id="a"),  # 1 event
            _ev(100, 1, 10, route_id="b"),  # 2 events
            _ev(100, -1, -100, route_id="b"),
        ]
        rows = partners_for_item(events, 100)
        assert rows[0].route_id == "b"
        assert rows[1].route_id == "a"

    def test_missing_partner_classified_unknown(self) -> None:
        events = [_ev(100, 1, 10, route_id=None, partner=None)]
        rows = partners_for_item(events, 100)
        assert rows[0].partner_kind == "unknown"
        assert rows[0].partner_id is None
        assert rows[0].route_id is None

    def test_display_partner_prefers_route_over_partner_id(self) -> None:
        ev_with_route = _ev(100, 1, 10, route_id="42", kind="route")
        ev_passive = _ev(
            100,
            1,
            10,
            route_id=None,
            partner=TradingPartner(id="99", display_name="npc", kind="passive"),
        )
        ev_nothing = _ev(100, 1, 10, route_id=None, partner=None)
        rows = partners_for_item([ev_with_route, ev_passive, ev_nothing], 100)
        labels = {r.display_partner for r in rows}
        assert "route #42" in labels
        assert "partner #99" in labels
        assert "—" in labels

    def test_display_partner_uses_route_name_when_present(self) -> None:
        """route_name があれば ``route <name>`` を優先．"""
        events = [_ev(100, 1, 10, route_id="42", kind="route", route_name="商会ルート")]
        rows = partners_for_item(events, 100)
        assert rows[0].route_name == "商会ルート"
        assert rows[0].display_partner == "route 商会ルート"

    def test_display_name_helper(self) -> None:
        events = [_ev(100, 1, 10, route_id="r")]
        rows = partners_for_item(events, 100)
        assert rows[0].display_name("en") == "Good_100"


class TestFilterEvents:
    def test_no_filter_returns_all(self) -> None:
        events = [_ev(1, 1, 1, session_id="0", island_name="A"), _ev(2, 1, 1, session_id="1")]
        assert len(filter_events(events)) == 2

    def test_filter_by_session(self) -> None:
        events = [
            _ev(1, 1, 1, session_id="0"),
            _ev(2, 1, 1, session_id="1"),
            _ev(3, 1, 1, session_id="0"),
        ]
        out = filter_events(events, session="0")
        assert len(out) == 2
        assert all(e.session_id == "0" for e in out)

    def test_filter_by_island(self) -> None:
        events = [
            _ev(1, 1, 1, island_name="大阪民国"),
            _ev(2, 1, 1, island_name="ジョウト地方"),
        ]
        out = filter_events(events, island="大阪民国")
        assert len(out) == 1
        assert out[0].island_name == "大阪民国"

    def test_filter_session_and_island_are_anded(self) -> None:
        events = [
            _ev(1, 1, 1, session_id="0", island_name="A"),
            _ev(2, 1, 1, session_id="0", island_name="B"),
            _ev(3, 1, 1, session_id="1", island_name="A"),
        ]
        out = filter_events(events, session="0", island="A")
        assert len(out) == 1
        assert out[0].item.guid == 1


class TestAggregateFilterArgs:
    def test_by_item_with_island_filter(self) -> None:
        events = [
            _ev(100, 5, 50, island_name="Osaka"),
            _ev(100, 3, 30, island_name="Gunma"),
        ]
        rows = by_item(events, island="Osaka")
        assert len(rows) == 1
        assert rows[0].bought == 5

    def test_by_route_with_session_filter(self) -> None:
        events = [
            _ev(1, 1, 10, route_id="A", kind="route", session_id="0"),
            _ev(1, 1, 10, route_id="A", kind="route", session_id="1"),
        ]
        rows = by_route(events, session="0")
        assert len(rows) == 1
        assert rows[0].event_count == 1

    def test_partners_for_item_with_island_filter(self) -> None:
        events = [
            _ev(100, 1, 10, route_id="A", island_name="X"),
            _ev(100, 1, 10, route_id="B", island_name="Y"),
        ]
        rows = partners_for_item(events, 100, island="X")
        assert len(rows) == 1
        assert rows[0].route_id == "A"
