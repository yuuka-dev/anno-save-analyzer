"""TradeEvent ストリームの集計．"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from pydantic import BaseModel

from .models import Item, Locale, TradeEvent


def filter_events(
    events: Iterable[TradeEvent],
    *,
    session: str | None = None,
    island: str | None = None,
) -> list[TradeEvent]:
    """session / island 粒度で TradeEvent stream を絞る．

    両方 ``None`` なら全量 (listify のみ)．両方指定時は AND．TUI の Tree
    選択や CLI ``--session`` / ``--island`` の共通入口．
    """
    out: list[TradeEvent] = []
    for ev in events:
        if session is not None and ev.session_id != session:
            continue
        if island is not None and ev.island_name != island:
            continue
        out.append(ev)
    return out


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


class PartnerSummary(BaseModel):
    """物資 × 取引相手 (route / partner) の集計．Partners pane の入力．"""

    item: Item
    route_id: str | None
    partner_id: str | None
    partner_kind: str
    bought: int = 0
    sold: int = 0
    net_gold: int = 0
    event_count: int = 0

    model_config = {"frozen": True}

    def display_name(self, locale: Locale) -> str:
        return self.item.display_name(locale)

    @property
    def display_partner(self) -> str:
        """partner pane で表示する相手ラベル．route 優先，無ければ partner_id．"""
        if self.route_id is not None:
            return f"route #{self.route_id}"
        if self.partner_id is not None:
            return f"partner #{self.partner_id}"
        return "—"


def by_item(
    events: Iterable[TradeEvent],
    *,
    session: str | None = None,
    island: str | None = None,
) -> list[ItemSummary]:
    """物資別に集計する．event_count 降順 → guid 昇順で安定ソート．

    ``session`` / ``island`` が指定されていればその粒度で pre-filter する．
    """
    if session is not None or island is not None:
        events = filter_events(events, session=session, island=island)
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


def by_route(
    events: Iterable[TradeEvent],
    *,
    session: str | None = None,
    island: str | None = None,
) -> list[RouteSummary]:
    """ルート / partner kind 別に集計．`(route_id, partner_kind)` キー．

    ``session`` / ``island`` が指定されていればその粒度で pre-filter する．
    """
    if session is not None or island is not None:
        events = filter_events(events, session=session, island=island)
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


def partners_for_item(
    events: Iterable[TradeEvent],
    item_guid: int,
    *,
    session: str | None = None,
    island: str | None = None,
) -> list[PartnerSummary]:
    """指定 item GUID の取引を (route_id, partner_id, kind) 別に集計．

    物資を選んだときの Partners pane に出す "この物資を誰と取引したか" を
    event_count 降順 → abs(net_gold) 降順 → route_id 昇順で返す．
    ``session`` / ``island`` 指定で絞り込み可能．
    """
    if session is not None or island is not None:
        events = filter_events(events, session=session, island=island)
    buckets: dict[tuple[str | None, str | None, str], dict] = defaultdict(
        lambda: {
            "bought": 0,
            "sold": 0,
            "net_gold": 0,
            "event_count": 0,
        }
    )
    item: Item | None = None
    for ev in events:
        if ev.item.guid != item_guid:
            continue
        item = ev.item
        kind = ev.partner.kind if ev.partner else "unknown"
        partner_id = ev.partner.id if ev.partner else None
        key = (ev.route_id, partner_id, kind)
        bucket = buckets[key]
        if ev.amount > 0:
            bucket["bought"] += ev.amount
        elif ev.amount < 0:
            bucket["sold"] += -ev.amount
        bucket["net_gold"] += ev.total_price
        bucket["event_count"] += 1

    if item is None:
        return []
    summaries = [
        PartnerSummary(
            item=item,
            route_id=route_id,
            partner_id=partner_id,
            partner_kind=kind,
            **bucket,
        )
        for (route_id, partner_id, kind), bucket in buckets.items()
    ]
    summaries.sort(key=lambda s: (-s.event_count, -abs(s.net_gold), s.route_id or ""))
    return summaries
