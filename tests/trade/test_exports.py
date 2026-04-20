"""trade.exports の単体テスト．"""

from __future__ import annotations

import csv
import io
import json

from anno_save_analyzer.trade import (
    ItemSummary,
    RouteSummary,
    TradeRouteDef,
    TransportTask,
    events_to_csv,
    events_to_json,
    items_to_csv,
    routes_to_csv,
)
from anno_save_analyzer.trade.models import Item, TradeEvent, TradingPartner


def _item(guid: int, name_en: str = "", name_ja: str = "") -> Item:
    names = {}
    if name_en:
        names["en"] = name_en
    if name_ja:
        names["ja"] = name_ja
    return Item(guid=guid, names=names)


class TestItemsToCsv:
    def test_writes_header_and_rows(self) -> None:
        summaries = [
            ItemSummary(
                item=_item(100, name_en="Wood"),
                bought=10,
                sold=3,
                net_qty=7,
                net_gold=-50,
                event_count=2,
                last_seen_tick=42,
            ),
            ItemSummary(
                item=_item(200, name_en="Bricks"),
                bought=1,
                sold=0,
                net_qty=1,
                net_gold=5,
                event_count=1,
            ),
        ]
        out = items_to_csv(summaries)
        reader = list(csv.reader(io.StringIO(out)))
        assert reader[0] == [
            "guid",
            "name",
            "bought",
            "sold",
            "net_qty",
            "net_gold",
            "event_count",
            "last_seen_tick",
        ]
        assert reader[1][:2] == ["100", "Wood"]
        assert reader[1][-1] == "42"
        # last_seen_tick 無しは空文字
        assert reader[2][-1] == ""

    def test_respects_locale(self) -> None:
        summaries = [
            ItemSummary(
                item=_item(100, name_en="Wood", name_ja="木材"),
                bought=0,
                sold=0,
                net_qty=0,
                net_gold=0,
                event_count=0,
            )
        ]
        out = items_to_csv(summaries, locale="ja")
        assert "木材" in out
        assert "Wood" not in out

    def test_empty_returns_header_only(self) -> None:
        out = items_to_csv([])
        rows = list(csv.reader(io.StringIO(out)))
        assert len(rows) == 1
        assert rows[0][0] == "guid"


class TestRoutesToCsv:
    def test_active_and_idle_rows_emitted(self) -> None:
        summaries = [
            RouteSummary(
                route_id="7",
                partner_kind="route",
                bought=10,
                sold=0,
                net_gold=100,
                event_count=3,
            ),
        ]
        idle = [
            TradeRouteDef(
                ship_id=99,
                route_hash=1,
                round_travel=0,
                establish_time=0,
                tasks=(
                    TransportTask(from_key=1, to_key=2, product_guid=100, balance_raw=0),
                    TransportTask(from_key=2, to_key=1, product_guid=200, balance_raw=0),
                ),
            ),
            # active=7 にも定義あり → legs_by_ship に積まれる
            TradeRouteDef(
                ship_id=7,
                route_hash=7,
                round_travel=0,
                establish_time=0,
                tasks=(TransportTask(from_key=9, to_key=9, product_guid=100, balance_raw=0),),
            ),
        ]
        out = routes_to_csv(summaries, idle_routes=idle, active_ids=("7",))
        rows = list(csv.reader(io.StringIO(out)))
        assert rows[0] == [
            "route_id",
            "route_name",
            "status",
            "partner_kind",
            "legs",
            "bought",
            "sold",
            "net_gold",
            "event_count",
        ]
        # active row (route_id=7) の legs は idle_routes 由来で 1
        active_row = next(r for r in rows[1:] if r[0] == "7")
        assert active_row[2] == "active"
        assert active_row[4] == "1"
        # idle row (ship=99) は status=idle
        idle_row = next(r for r in rows[1:] if r[0] == "99")
        assert idle_row[2] == "idle"
        assert idle_row[4] == "2"

    def test_idle_routes_with_none_ship_id_skipped(self) -> None:
        idle = [
            TradeRouteDef(
                ship_id=None, route_hash=None, round_travel=None, establish_time=None, tasks=()
            )
        ]
        out = routes_to_csv([], idle_routes=idle)
        rows = list(csv.reader(io.StringIO(out)))
        assert len(rows) == 1  # header only

    def test_active_summary_without_route_id_falls_through(self) -> None:
        """route_id=None の RouteSummary (passive) も emit される (rid=空文字)．"""
        summaries = [
            RouteSummary(
                route_id=None, partner_kind="passive", bought=0, sold=2, net_gold=-5, event_count=1
            )
        ]
        out = routes_to_csv(summaries)
        rows = list(csv.reader(io.StringIO(out)))
        assert len(rows) == 2
        assert rows[1][0] == ""  # route_id
        assert rows[1][1] == ""  # route_name
        assert rows[1][2] == "active"

    def test_active_summary_with_route_name_emits_name_column(self) -> None:
        """RouteSummary.route_name が route_name 列に流れ込む．"""
        summaries = [
            RouteSummary(
                route_id="7",
                partner_kind="route",
                bought=10,
                sold=0,
                net_gold=100,
                event_count=3,
                route_name="商会ルート",
            )
        ]
        out = routes_to_csv(summaries)
        rows = list(csv.reader(io.StringIO(out)))
        assert rows[1][0] == "7"
        assert rows[1][1] == "商会ルート"

    def test_idle_route_already_in_active_ids_is_skipped(self) -> None:
        """active_ids に含まれる ship_id は idle として重複出力しない．"""
        idle = [
            TradeRouteDef(
                ship_id=7,
                route_hash=1,
                round_travel=0,
                establish_time=0,
                tasks=(TransportTask(from_key=1, to_key=2, product_guid=1, balance_raw=0),),
            )
        ]
        out = routes_to_csv([], idle_routes=idle, active_ids=("7",))
        rows = list(csv.reader(io.StringIO(out)))
        # header + idle=0 (active_ids により除外)
        assert len(rows) == 1


class TestEventsToCsvAndJson:
    def _ev(self, guid=100, amount=1, price=10, **kwargs) -> TradeEvent:
        item = _item(guid, name_en=f"Item{guid}", name_ja=f"品{guid}")
        partner = kwargs.pop(
            "partner",
            TradingPartner(id="7", display_name="r", kind="route"),
        )
        return TradeEvent(
            item=item,
            amount=amount,
            total_price=price,
            partner=partner,
            **kwargs,
        )

    def test_events_csv_has_all_columns(self) -> None:
        events = [
            self._ev(route_id="7", session_id="0", timestamp_tick=100, route_name="商会ルート"),
            self._ev(guid=200, amount=-2, price=-50, partner=None, session_id=None),
        ]
        out = events_to_csv(events)
        rows = list(csv.reader(io.StringIO(out)))
        assert rows[0] == [
            "timestamp_tick",
            "session_id",
            "island_name",
            "route_id",
            "route_name",
            "partner_id",
            "partner_kind",
            "item_guid",
            "item_name",
            "amount",
            "total_price",
        ]
        assert rows[1][0] == "100"  # timestamp
        assert rows[1][4] == "商会ルート"  # route_name
        assert rows[1][7] == "100"  # item_guid
        # 2 行目 partner=None
        assert rows[2][4] == ""  # route_name
        assert rows[2][5] == ""  # partner_id
        assert rows[2][6] == ""  # partner_kind
        # timestamp 無し
        assert rows[2][0] == ""

    def test_events_csv_respects_locale(self) -> None:
        events = [self._ev(guid=100)]
        out = events_to_csv(events, locale="ja")
        assert "品100" in out

    def test_events_json_round_trip(self) -> None:
        events = [
            self._ev(route_id="7", session_id="0", timestamp_tick=100),
            self._ev(guid=200, amount=-2, partner=None),
        ]
        out = events_to_json(events)
        parsed = json.loads(out)
        assert len(parsed) == 2
        assert parsed[0]["item"]["guid"] == 100
        assert parsed[0]["partner"] == {"id": "7", "kind": "route"}
        assert parsed[1]["partner"] is None

    def test_events_json_is_utf8_not_escaped(self) -> None:
        events = [self._ev(guid=100)]
        out = events_to_json(events, locale="ja")
        assert "品100" in out  # ensure_ascii=False なので生の日本語が出る

    def test_events_csv_includes_island_name(self) -> None:
        events = [
            self._ev(route_id="7", session_id="0", timestamp_tick=100, island_name="大阪民国")
        ]
        out = events_to_csv(events)
        rows = list(csv.reader(io.StringIO(out)))
        # island_name 列は index 2
        assert rows[1][2] == "大阪民国"

    def test_events_json_includes_island_name(self) -> None:
        events = [self._ev(island_name="Osaka")]
        parsed = json.loads(events_to_json(events))
        assert parsed[0]["island_name"] == "Osaka"


class TestInventoryToCsv:
    def _items_dict(self, locales=("en",)):
        from anno_save_analyzer.trade import GameTitle, ItemDictionary

        return ItemDictionary.load(GameTitle.ANNO_117, locales=locales)

    def test_writes_header_and_rows(self) -> None:
        from anno_save_analyzer.trade import (
            IslandStorageTrend,
            PointSeries,
            inventory_to_csv,
        )

        trends = [
            IslandStorageTrend(
                island_name="大阪民国",
                product_guid=2077,
                last_point_tick=144380000,
                estimation=0,
                points=PointSeries(capacity=3, size=3, samples=(1, 2, 3)),
            ),
            IslandStorageTrend(
                island_name="ジョウト地方",
                product_guid=2088,
                last_point_tick=None,
                estimation=None,
                points=PointSeries(capacity=3, size=3, samples=(5, 5, 5)),
            ),
        ]
        out = inventory_to_csv(trends, items=self._items_dict(), locale="en")
        rows = list(csv.reader(io.StringIO(out)))
        assert rows[0] == [
            "island_name",
            "product_guid",
            "product_name",
            "latest",
            "peak",
            "mean",
            "slope",
            "last_point_tick",
            "samples",
        ]
        # 1 行目: 大阪民国 + Wood (2077)
        assert rows[1][0] == "大阪民国"
        assert rows[1][1] == "2077"
        assert rows[1][2] == "Wood"
        assert rows[1][3] == "3"  # latest
        assert rows[1][4] == "3"  # peak
        assert rows[1][7] == "144380000"
        assert rows[1][8] == "1|2|3"
        # 2 行目: last_point_tick 無し → 空
        assert rows[2][7] == ""

    def test_respects_locale(self) -> None:
        from anno_save_analyzer.trade import (
            IslandStorageTrend,
            PointSeries,
            inventory_to_csv,
        )

        trends = [
            IslandStorageTrend(
                island_name="x",
                product_guid=2088,
                points=PointSeries(capacity=1, size=1, samples=(5,)),
            )
        ]
        out = inventory_to_csv(trends, items=self._items_dict(locales=("en", "ja")), locale="ja")
        # 2088 = Sardines (en) / イワシ (ja)
        assert "イワシ" in out

    def test_empty_returns_header_only(self) -> None:
        from anno_save_analyzer.trade import inventory_to_csv

        out = inventory_to_csv([], items=self._items_dict())
        assert len(list(csv.reader(io.StringIO(out)))) == 1
