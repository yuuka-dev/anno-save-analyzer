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
    route_name: str | None = None
    """書記長命名のルート名．``partner_kind='route'`` のみ．表示では
    ``route_name`` 優先，無ければ ``route_id`` を fallback．
    """

    model_config = {"frozen": True}

    @property
    def display_route(self) -> str:
        """routes-table 向け表示ラベル．route_name > ``#{route_id}`` > ``—``．"""
        if self.route_name:
            return self.route_name
        if self.route_id is not None:
            return f"#{self.route_id}"
        return "—"


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
    route_name: str | None = None

    model_config = {"frozen": True}

    def display_name(self, locale: Locale) -> str:
        return self.item.display_name(locale)

    @property
    def display_partner(self) -> str:
        """partner pane で表示する相手ラベル．route_name > route_id > partner_id．"""
        if self.route_name:
            return f"route {self.route_name}"
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
            "route_name": None,
        }
    )
    route_name_latest_tick_by_key: dict[tuple[str | None, str], int | None] = {}
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
        # route_name は同一 route_id 内で変わる可能性 (書記長が途中で rename)．
        # route_name 用の最新 tick を別管理し，入力順に依存せず最新 rename を採用する．
        if ev.route_name:
            route_name_tick = ev.timestamp_tick
            current_name_tick = route_name_latest_tick_by_key.get(key)
            if route_name_tick is None:
                if bucket["route_name"] is None:
                    bucket["route_name"] = ev.route_name
            elif current_name_tick is None or route_name_tick > current_name_tick:
                bucket["route_name"] = ev.route_name
                route_name_latest_tick_by_key[key] = route_name_tick

    summaries = [
        RouteSummary(route_id=route_id, partner_kind=kind, **bucket)
        for (route_id, kind), bucket in buckets.items()
    ]
    summaries.sort(key=lambda s: (-s.event_count, s.route_id or ""))
    return summaries


def events_for_item(
    events: Iterable[TradeEvent],
    item_guid: int,
    *,
    session: str | None = None,
    island: str | None = None,
    limit: int = 50,
) -> list[TradeEvent]:
    """指定 item の TradeEvent を ``timestamp_tick`` 降順で最大 ``limit`` 件返す．

    「この物資を最近いつ取引したか」を Partners pane 下に並べる用途．集計を行わず
    個別 event を素通しで渡す．``timestamp_tick=None`` の event は末尾に寄せる．
    ``session`` / ``island`` 指定で事前フィルタ．``limit`` に負値を渡すと上限なし．
    """
    if session is not None or island is not None:
        events = filter_events(events, session=session, island=island)
    filtered = [ev for ev in events if ev.item.guid == item_guid]
    # tick=None を末尾へ → (is_none, -tick) で降順．
    filtered.sort(key=lambda e: (e.timestamp_tick is None, -(e.timestamp_tick or 0)))
    if limit < 0:
        return filtered
    return filtered[:limit]


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
            "route_name": None,
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
        if ev.route_name and bucket["route_name"] is None:
            bucket["route_name"] = ev.route_name

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
