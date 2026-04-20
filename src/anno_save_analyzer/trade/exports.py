"""CSV / JSON エクスポート用の純関数．

TUI / CLI 両方から呼ばれるため副作用を持たず，str を返す．ファイル書き出しは
呼び出し側が行う．Windows/Unix 両対応のため改行は ``\\n`` で統一．
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable

from .aggregate import ItemSummary, RouteSummary
from .items import ItemDictionary
from .models import Locale, TradeEvent
from .routes import TradeRouteDef
from .storage import IslandStorageTrend


def _csv_writer(rows: list[list[str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerows(rows)
    return buf.getvalue()


def items_to_csv(summaries: Iterable[ItemSummary], *, locale: Locale = "en") -> str:
    """物資別サマリを CSV にエクスポート．

    列: guid, name, bought, sold, net_qty, net_gold, event_count, last_seen_tick
    """
    rows: list[list[str]] = [
        ["guid", "name", "bought", "sold", "net_qty", "net_gold", "event_count", "last_seen_tick"]
    ]
    for s in summaries:
        rows.append(
            [
                str(s.item.guid),
                s.display_name(locale),
                str(s.bought),
                str(s.sold),
                str(s.net_qty),
                str(s.net_gold),
                str(s.event_count),
                "" if s.last_seen_tick is None else str(s.last_seen_tick),
            ]
        )
    return _csv_writer(rows)


def routes_to_csv(
    summaries: Iterable[RouteSummary],
    *,
    idle_routes: Iterable[TradeRouteDef] = (),
    active_ids: Iterable[str] = (),
) -> str:
    """ルート別サマリ + idle route 定義を CSV にエクスポート．

    列: route_id, route_name, status, partner_kind, legs, bought, sold,
         net_gold, event_count
    """
    active = set(active_ids)
    legs_by_ship: dict[str, int] = {}
    idle_list = list(idle_routes)
    for rd in idle_list:
        if rd.ship_id is not None:
            legs_by_ship[str(rd.ship_id)] = len(rd.tasks)

    rows: list[list[str]] = [
        [
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
    ]
    seen: set[str] = set()
    for s in summaries:
        rid = s.route_id or ""
        legs = legs_by_ship.get(rid, 0)
        rows.append(
            [
                rid,
                s.route_name or "",
                "active",
                s.partner_kind,
                str(legs),
                str(s.bought),
                str(s.sold),
                str(s.net_gold),
                str(s.event_count),
            ]
        )
        if rid:
            seen.add(rid)
    # idle = 定義あり / 履歴無し．active_ids に含まれないもののみ出す．
    # idle 側は route_name を持たない (定義側の attrib は未読)．空文字で出力．
    for rd in idle_list:
        if rd.ship_id is None:
            continue
        rid = str(rd.ship_id)
        if rid in active or rid in seen:
            continue
        rows.append([rid, "", "idle", "route", str(len(rd.tasks)), "0", "0", "0", "0"])
        seen.add(rid)
    return _csv_writer(rows)


def events_to_csv(events: Iterable[TradeEvent], *, locale: Locale = "en") -> str:
    """個別 TradeEvent を CSV にエクスポート (ledger 全量)．

    列: timestamp_tick, session_id, island_name, route_id, route_name,
         partner_id, partner_kind, item_guid, item_name, amount, total_price
    """
    rows: list[list[str]] = [
        [
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
    ]
    for ev in events:
        partner_id = ev.partner.id if ev.partner else ""
        partner_kind = ev.partner.kind if ev.partner else ""
        rows.append(
            [
                "" if ev.timestamp_tick is None else str(ev.timestamp_tick),
                ev.session_id or "",
                ev.island_name or "",
                ev.route_id or "",
                ev.route_name or "",
                partner_id,
                partner_kind,
                str(ev.item.guid),
                ev.item.display_name(locale),
                str(ev.amount),
                str(ev.total_price),
            ]
        )
    return _csv_writer(rows)


def inventory_to_csv(
    trends: Iterable[IslandStorageTrend],
    *,
    items: ItemDictionary,
    locale: Locale = "en",
) -> str:
    """島 × 物資の在庫時系列 (StorageTrends) を CSV にエクスポート．

    列: island_name, product_guid, product_name, latest, peak, mean, slope,
         last_point_tick, samples (120 値を ``|`` 区切り)
    """
    rows: list[list[str]] = [
        [
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
    ]
    for tr in trends:
        name = items[tr.product_guid].display_name(locale)
        rows.append(
            [
                tr.island_name,
                str(tr.product_guid),
                name,
                str(tr.latest),
                str(tr.peak),
                f"{tr.points.mean:.2f}",
                f"{tr.points.slope:.4f}",
                "" if tr.last_point_tick is None else str(tr.last_point_tick),
                "|".join(str(v) for v in tr.points.samples),
            ]
        )
    return _csv_writer(rows)


def events_to_json(events: Iterable[TradeEvent], *, locale: Locale = "en") -> str:
    """TradeEvent を JSON 配列にエクスポート (human-readable / 2-space indent)．"""
    data = []
    for ev in events:
        data.append(
            {
                "timestamp_tick": ev.timestamp_tick,
                "session_id": ev.session_id,
                "island_name": ev.island_name,
                "route_id": ev.route_id,
                "route_name": ev.route_name,
                "partner": ({"id": ev.partner.id, "kind": ev.partner.kind} if ev.partner else None),
                "item": {
                    "guid": ev.item.guid,
                    "name": ev.item.display_name(locale),
                },
                "amount": ev.amount,
                "total_price": ev.total_price,
            }
        )
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
