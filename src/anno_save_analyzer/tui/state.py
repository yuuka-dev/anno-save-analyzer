"""TUI が消費する事前計算済み状態．純粋データ層に閉じ込めて UI と切り離す．

これにより TUI 描画は副作用なし純粋関数の出力を表示するだけになり，
テストは UI を起動せず ``TuiState`` を直接組み立てて検証できる．
"""

from __future__ import annotations

import zlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from anno_save_analyzer.parser.filedb import (
    detect_version,
    extract_sessions,
    list_inner_area_managers,
    parse_tag_section,
)
from anno_save_analyzer.parser.pipeline import extract_inner_filedb
from anno_save_analyzer.trade import (
    GameTitle,
    ItemDictionary,
    by_item,
    by_route,
    extract,
)
from anno_save_analyzer.trade.aggregate import ItemSummary, RouteSummary
from anno_save_analyzer.trade.models import TradeEvent
from anno_save_analyzer.trade.sessions import session_locale_key


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
    # session_id (= "0" / "1" ...) → locale lookup key (例 "session.anno117.latium")
    # localizer 経由で「Latium / ラティウム」等にレンダリングする．
    session_locale_keys: tuple[str, ...] = field(default_factory=tuple)
    # session_id → AreaManager_<N> の N 群．Statistics 画面の Tree で
    # session > AreaManager の階層を組むのに使う．
    islands_by_session: dict[str, tuple[int, ...]] = field(default_factory=dict)


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
    locale_keys = tuple(
        session_locale_key(title, int(sid)) if sid.isdigit() else "session.unknown"
        for sid in overview.session_ids
    )

    # 内側 Session の AreaManager_* 列挙．Tree の島階層に使う．
    islands_by_session = _collect_islands_by_session(save_path, overview.session_ids)

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
        session_locale_keys=locale_keys,
        islands_by_session=islands_by_session,
    )


def _collect_islands_by_session(
    save_path: Path, session_ids: tuple[str, ...]
) -> dict[str, tuple[int, ...]]:
    """内側 Session ごとに ``AreaManager_<N>`` を列挙．

    Anno のセーブでは 1 島 = 1 ``AreaManager``．tag 辞書を読むだけでよい．
    """
    if not session_ids:
        return {}
    suffix = save_path.suffix.lower()
    if suffix in {".a7s", ".a8s"}:
        outer = extract_inner_filedb(save_path)
    else:
        raw = save_path.read_bytes()
        outer = zlib.decompress(raw) if raw[:2] in (b"\x78\x9c", b"\x78\xda", b"\x78\x01") else raw
    version = detect_version(outer)
    section = parse_tag_section(outer, version)
    inner_payloads = extract_sessions(outer, version=version, tag_section=section)

    by_session: dict[str, tuple[int, ...]] = {}
    for sid, inner in zip(session_ids, inner_payloads, strict=False):
        by_session[sid] = list_inner_area_managers(inner)
    return by_session
