"""2 セーブ間のトレード差分を計算する純関数．

書記長のユースケースは「前回保存 → 今回保存の間に何がどう動いたか」．
CLI から呼び出されるが，純関数レベルでテストできるよう副作用は持たない．
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel

from .aggregate import by_item, by_route
from .models import Item, Locale, TradeEvent


class ItemDelta(BaseModel):
    """Item GUID ごとの before → after 差分．

    - ``bought_delta`` / ``sold_delta`` / ``event_count_delta`` は単純な差
    - ``net_gold_delta`` / ``net_qty_delta`` は累積値の差
    - ``status``: ``"added"`` (before に無い) / ``"removed"`` (after に無い) /
      ``"changed"`` (両方にあり値変動) / ``"unchanged"`` (完全一致)
    """

    item: Item
    bought_delta: int
    sold_delta: int
    net_qty_delta: int
    net_gold_delta: int
    event_count_delta: int
    status: str

    model_config = {"frozen": True}

    def display_name(self, locale: Locale) -> str:
        return self.item.display_name(locale)


class RouteDelta(BaseModel):
    """``(route_id, partner_kind)`` ごとの before → after 差分．"""

    route_id: str | None
    partner_kind: str
    bought_delta: int
    sold_delta: int
    net_gold_delta: int
    event_count_delta: int
    status: str

    model_config = {"frozen": True}


def _sign(n: int) -> int:
    return (n > 0) - (n < 0)


def _classify(before_count: int, after_count: int, nonzero_delta: bool) -> str:
    if before_count == 0 and after_count > 0:
        return "added"
    if before_count > 0 and after_count == 0:
        return "removed"
    if nonzero_delta:
        return "changed"
    return "unchanged"


def diff_by_item(
    before: Iterable[TradeEvent],
    after: Iterable[TradeEvent],
    *,
    session: str | None = None,
    island: str | None = None,
) -> list[ItemDelta]:
    """物資別に before / after を集計し delta を算出．event_count 降順 → guid 昇順で返す．

    ``session`` / ``island`` 指定で両サイドを filter してから diff する．
    """
    b_summaries = {s.item.guid: s for s in by_item(before, session=session, island=island)}
    a_summaries = {s.item.guid: s for s in by_item(after, session=session, island=island)}
    guids = sorted(set(b_summaries) | set(a_summaries))
    deltas: list[ItemDelta] = []
    for guid in guids:
        b = b_summaries.get(guid)
        a = a_summaries.get(guid)
        # Item メタは存在するほうを採用 (after 優先，無ければ before)
        item = a.item if a is not None else b.item  # type: ignore[union-attr]
        bought_d = (a.bought if a else 0) - (b.bought if b else 0)
        sold_d = (a.sold if a else 0) - (b.sold if b else 0)
        qty_d = (a.net_qty if a else 0) - (b.net_qty if b else 0)
        gold_d = (a.net_gold if a else 0) - (b.net_gold if b else 0)
        count_d = (a.event_count if a else 0) - (b.event_count if b else 0)
        status = _classify(
            before_count=b.event_count if b else 0,
            after_count=a.event_count if a else 0,
            nonzero_delta=any(_sign(x) for x in (bought_d, sold_d, qty_d, gold_d, count_d)),
        )
        deltas.append(
            ItemDelta(
                item=item,
                bought_delta=bought_d,
                sold_delta=sold_d,
                net_qty_delta=qty_d,
                net_gold_delta=gold_d,
                event_count_delta=count_d,
                status=status,
            )
        )
    deltas.sort(key=lambda d: (-d.event_count_delta, d.item.guid))
    return deltas


def diff_by_route(
    before: Iterable[TradeEvent],
    after: Iterable[TradeEvent],
    *,
    session: str | None = None,
    island: str | None = None,
) -> list[RouteDelta]:
    """ルート × partner_kind 別の delta．キーは ``(route_id, partner_kind)``．

    ``session`` / ``island`` 指定で両サイドを filter してから diff する．
    """
    b_summaries = {
        (s.route_id, s.partner_kind): s for s in by_route(before, session=session, island=island)
    }
    a_summaries = {
        (s.route_id, s.partner_kind): s for s in by_route(after, session=session, island=island)
    }
    keys = sorted(set(b_summaries) | set(a_summaries), key=lambda k: (k[0] or "", k[1]))
    deltas: list[RouteDelta] = []
    for key in keys:
        b = b_summaries.get(key)
        a = a_summaries.get(key)
        route_id, kind = key
        bought_d = (a.bought if a else 0) - (b.bought if b else 0)
        sold_d = (a.sold if a else 0) - (b.sold if b else 0)
        gold_d = (a.net_gold if a else 0) - (b.net_gold if b else 0)
        count_d = (a.event_count if a else 0) - (b.event_count if b else 0)
        status = _classify(
            before_count=b.event_count if b else 0,
            after_count=a.event_count if a else 0,
            nonzero_delta=any(_sign(x) for x in (bought_d, sold_d, gold_d, count_d)),
        )
        deltas.append(
            RouteDelta(
                route_id=route_id,
                partner_kind=kind,
                bought_delta=bought_d,
                sold_delta=sold_d,
                net_gold_delta=gold_d,
                event_count_delta=count_d,
                status=status,
            )
        )
    deltas.sort(key=lambda d: (-d.event_count_delta, d.route_id or ""))
    return deltas
