"""tui.state のテスト．"""

from __future__ import annotations

from pathlib import Path

from anno_save_analyzer.trade import GameTitle, Item, TradingPartner
from anno_save_analyzer.trade.aggregate import ItemSummary, RouteSummary
from anno_save_analyzer.trade.models import TradeEvent
from anno_save_analyzer.tui.state import build_overview


def _ev(guid: int, amount: int, price: int, *, sid: str | None = "0") -> TradeEvent:
    item = Item(guid=guid, names={"en": f"Good_{guid}"})
    return TradeEvent(
        item=item,
        amount=amount,
        total_price=price,
        partner=TradingPartner(id="anon", display_name="x", kind="route"),
        session_id=sid,
        route_id="42",
    )


class TestBuildOverview:
    def test_collects_distinct_sessions_in_order(self, tmp_path: Path) -> None:
        events = [
            _ev(1, 1, 1, sid="0"),
            _ev(2, 1, 1, sid="1"),
            _ev(3, 1, 1, sid="0"),  # duplicate
            _ev(4, 1, 1, sid=None),  # session_id absent → ignored
        ]
        item_rows = (
            ItemSummary(
                item=Item(guid=1, names={}), bought=1, sold=0, net_qty=1, net_gold=1, event_count=1
            ),
        )
        route_rows = (
            RouteSummary(
                route_id="42", partner_kind="route", bought=4, sold=0, net_gold=4, event_count=4
            ),
        )
        snap = build_overview(tmp_path / "x.bin", GameTitle.ANNO_117, events, item_rows, route_rows)
        assert snap.session_ids == ("0", "1")
        assert snap.total_events == 4
        assert snap.distinct_goods == 1
        assert snap.distinct_routes == 1
        assert snap.net_gold == 4

    def test_empty_events_yields_zero_metrics(self, tmp_path: Path) -> None:
        snap = build_overview(tmp_path / "x.bin", GameTitle.ANNO_117, [], (), ())
        assert snap.session_ids == ()
        assert snap.total_events == 0
        assert snap.distinct_goods == 0
        assert snap.distinct_routes == 0
        assert snap.net_gold == 0


class TestLoadState:
    def test_loads_default_dictionary_when_items_omitted(self, tui_state) -> None:
        # tui_state fixture が items 渡してるので別 case で items=None を踏む
        from anno_save_analyzer.tui.state import load_state as ls

        save = tui_state.save_path
        new_state = ls(save, title=GameTitle.ANNO_117, locale="en")
        # 同梱辞書を読むはずなので取れる guid は同梱の 20 物資 + extracted unknown guids
        assert new_state.overview.total_events == tui_state.overview.total_events

    def test_load_state_with_ja_locale(self, tmp_path: Path, tui_state) -> None:
        from anno_save_analyzer.tui.state import load_state as ls

        save = tui_state.save_path
        ja = ls(save, title=GameTitle.ANNO_117, locale="ja")
        assert ja.locale == "ja"
