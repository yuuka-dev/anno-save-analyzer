"""TUI が消費する事前計算済み状態．純粋データ層に閉じ込めて UI と切り離す．

これにより TUI 描画は副作用なし純粋関数の出力を表示するだけになり，
テストは UI を起動せず ``TuiState`` を直接組み立てて検証できる．
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from anno_save_analyzer.trade import (
    GameTitle,
    ItemDictionary,
    by_item,
    by_route,
    extract,
)
from anno_save_analyzer.trade.aggregate import ItemSummary, RouteSummary
from anno_save_analyzer.trade.models import TradeEvent


@dataclass(frozen=True)
class OverviewSnapshot:
    """Overview 画面が表示する固定値．"""

    save_path: Path
    title: GameTitle
    session_ids: tuple[str, ...]
    total_events: int
    distinct_goods: int
    distinct_routes: int
    net_gold: int


@dataclass(frozen=True)
class TuiState:
    """全画面共通で参照する事前計算済み state．"""

    save_path: Path
    title: GameTitle
    locale: str
    events: tuple[TradeEvent, ...]
    items: ItemDictionary
    overview: OverviewSnapshot
    item_summaries: tuple[ItemSummary, ...]
    route_summaries: tuple[RouteSummary, ...]
    session_ids: tuple[str, ...] = field(default_factory=tuple)


def build_overview(
    save_path: Path,
    title: GameTitle,
    events: Iterable[TradeEvent],
    item_summaries: Iterable[ItemSummary],
    route_summaries: Iterable[RouteSummary],
) -> OverviewSnapshot:
    events_list = list(events)
    sessions: list[str] = []
    seen: set[str] = set()
    net_gold = 0
    for ev in events_list:
        if ev.session_id and ev.session_id not in seen:
            seen.add(ev.session_id)
            sessions.append(ev.session_id)
        net_gold += ev.total_price

    distinct_goods = sum(1 for _ in item_summaries)
    distinct_routes = sum(1 for _ in route_summaries)

    return OverviewSnapshot(
        save_path=save_path,
        title=title,
        session_ids=tuple(sessions),
        total_events=len(events_list),
        distinct_goods=distinct_goods,
        distinct_routes=distinct_routes,
        net_gold=net_gold,
    )


def load_state(
    save_path: Path,
    *,
    title: GameTitle,
    locale: str = "en",
    items: ItemDictionary | None = None,
) -> TuiState:
    """セーブを読み込み，TUI 用 state を構築する．

    呼び出し側がすでに ``ItemDictionary`` を持っているなら ``items`` で渡せる
    （二重ロード回避）．
    """
    if items is None:
        locales: tuple[str, ...] = ("en",) if locale == "en" else ("en", locale)
        items = ItemDictionary.load(title, locales=locales)

    events = list(extract(save_path, title=title, items=items))
    item_rows = by_item(events)
    route_rows = by_route(events)
    overview = build_overview(save_path, title, events, item_rows, route_rows)
    return TuiState(
        save_path=save_path,
        title=title,
        locale=locale,
        events=tuple(events),
        items=items,
        overview=overview,
        item_summaries=tuple(item_rows),
        route_summaries=tuple(route_rows),
        session_ids=overview.session_ids,
    )
