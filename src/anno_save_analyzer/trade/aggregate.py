"""TradeEvent ストリームの集計．"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from pydantic import BaseModel

from .models import Item, Locale, TradeEvent


class ItemSummary(BaseModel):
    """物資別集計．"""

    item: Item
    bought: int = 0
    sold: int = 0
    net_qty: int = 0
    net_gold: int = 0
    event_count: int = 0
    last_seen_tick: int | None = None

    model_config = {"frozen": True}

    def display_name(self, locale: Locale) -> str:
        return self.item.display_name(locale)


class RouteSummary(BaseModel):
    """ルート / パートナー別集計．"""

    route_id: str | None
    partner_kind: str
    bought: int = 0
    sold: int = 0
    net_gold: int = 0
    event_count: int = 0
    last_seen_tick: int | None = None

    model_config = {"frozen": True}


def by_item(events: Iterable[TradeEvent]) -> list[ItemSummary]:
    """物資別に集計する．event_count 降順 → guid 昇順で安定ソート．"""
    buckets: dict[int, dict] = {}
    item_lookup: dict[int, Item] = {}
    for ev in events:
        guid = ev.item.guid
        item_lookup.setdefault(guid, ev.item)
        bucket = buckets.setdefault(
            guid,
            {
                "bought": 0,
                "sold": 0,
                "net_qty": 0,
                "net_gold": 0,
                "event_count": 0,
                "last_seen_tick": None,
            },
        )
        if ev.amount > 0:
            bucket["bought"] += ev.amount
        elif ev.amount < 0:
            bucket["sold"] += -ev.amount
        bucket["net_qty"] += ev.amount
        bucket["net_gold"] += ev.total_price
        bucket["event_count"] += 1
        if ev.timestamp_tick is not None:
            current = bucket["last_seen_tick"]
            if current is None or ev.timestamp_tick > current:
                bucket["last_seen_tick"] = ev.timestamp_tick

    summaries = [ItemSummary(item=item_lookup[g], **bucket) for g, bucket in buckets.items()]
    summaries.sort(key=lambda s: (-s.event_count, s.item.guid))
    return summaries


def by_route(events: Iterable[TradeEvent]) -> list[RouteSummary]:
    """ルート / partner kind 別に集計．`(route_id, partner_kind)` キー．"""
    buckets: dict[tuple[str | None, str], dict] = defaultdict(
        lambda: {
            "bought": 0,
            "sold": 0,
            "net_gold": 0,
            "event_count": 0,
            "last_seen_tick": None,
        }
    )
    for ev in events:
        kind = ev.partner.kind if ev.partner else "unknown"
        key = (ev.route_id, kind)
        bucket = buckets[key]
        if ev.amount > 0:
            bucket["bought"] += ev.amount
        elif ev.amount < 0:
            bucket["sold"] += -ev.amount
        bucket["net_gold"] += ev.total_price
        bucket["event_count"] += 1
        if ev.timestamp_tick is not None:
            current = bucket["last_seen_tick"]
            if current is None or ev.timestamp_tick > current:
                bucket["last_seen_tick"] = ev.timestamp_tick

    summaries = [
        RouteSummary(route_id=route_id, partner_kind=kind, **bucket)
        for (route_id, kind), bucket in buckets.items()
    ]
    summaries.sort(key=lambda s: (-s.event_count, s.route_id or ""))
    return summaries
