"""TUI が消費する事前計算済み状態．純粋データ層に閉じ込めて UI と切り離す．

これにより TUI 描画は副作用なし純粋関数の出力を表示するだけになり，
テストは UI を起動せず ``TuiState`` を直接組み立てて検証できる．
"""

from __future__ import annotations

import zlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from anno_save_analyzer.parser.filedb import (
    PlayerIsland,
    detect_version,
    extract_sessions,
    list_player_islands,
    parse_tag_section,
)
from anno_save_analyzer.parser.pipeline import extract_inner_filedb
from anno_save_analyzer.trade import (
    GameTitle,
    IslandStorageTrend,
    ItemDictionary,
    TradeRouteDef,
    by_item,
    by_route,
    list_storage_trends,
    list_trade_routes,
)
from anno_save_analyzer.trade.aggregate import ItemSummary, RouteSummary
from anno_save_analyzer.trade.extract import extract_from_outer, load_outer_filedb
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
    # session_id → プレイヤー保有島 (CityName 持ち) のリスト．
    # Statistics 画面の Tree で session > island の階層に使う．
    islands_by_session: dict[str, tuple[PlayerIsland, ...]] = field(default_factory=dict)
    # session_id → 定義済 TradeRoute のリスト．
    # 履歴に現れない idle route も含まれる．Statistics 画面で active/idle 両方
    # を列挙するために使う．
    routes_by_session: dict[str, tuple[TradeRouteDef, ...]] = field(default_factory=dict)
    # island_name (CityName) → 在庫時系列 (物資別) のリスト．
    # Inventory tab の入力．session 横断キー (島名は全 session 合計でユニーク想定)．
    storage_by_island: dict[str, tuple[IslandStorageTrend, ...]] = field(default_factory=dict)


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


def _decompress_outer(save_path: Path) -> tuple[bytes, list[bytes]]:
    """outer FileDB を 1 度だけ解凍し inner session payloads も抽出．

    Cursor レビュー指摘 #1 対応: ``load_state`` の責務を機能単位に分解し，
    outer 解凍ロジックを単体でテスト / 差し替え可能にする．
    """
    outer_filedb = load_outer_filedb(save_path)
    version = detect_version(outer_filedb)
    section = parse_tag_section(outer_filedb, version)
    inner_payloads = extract_sessions(outer_filedb, version=version, tag_section=section)
    return outer_filedb, inner_payloads


def _build_aggregates_and_overview(
    save_path: Path, title: GameTitle, events: list[TradeEvent]
) -> tuple[list[ItemSummary], list[RouteSummary], OverviewSnapshot, tuple[str, ...]]:
    """events から集計 (item / route)，Overview，session locale keys を作る．"""
    item_rows = by_item(events)
    route_rows = by_route(events)
    overview = build_overview(save_path, title, events, item_rows, route_rows)
    locale_keys = tuple(
        session_locale_key(title, int(sid)) if sid.isdigit() else "session.unknown"
        for sid in overview.session_ids
    )
    return item_rows, route_rows, overview, locale_keys


def load_state(
    save_path: Path,
    *,
    title: GameTitle,
    locale: str = "en",
    items: ItemDictionary | None = None,
    progress: Callable[[str], None] | None = None,
) -> TuiState:
    """セーブを読み込み，TUI 用 state を構築する．

    ``progress`` callback を渡すと各ステージ開始時にラベルを通知する
    (CLI 側でプログレスバーを描画する用)．``items`` を渡せば辞書ロードを
    スキップできる．

    オーケストレーション本体．outer 解凍や集計は private helper に委譲し，
    この関数はステージの連結とステート組み立てだけに責任を持つ．
    """
    if progress is None:

        def progress(_stage: str) -> None:
            pass

    if items is None:
        progress("loading item dictionary")
        locales: tuple[str, ...] = ("en",) if locale == "en" else ("en", locale)
        items = ItemDictionary.load(title, locales=locales)

    progress("extracting outer FileDB")
    outer_filedb, inner_payloads = _decompress_outer(save_path)

    progress("walking trade events")
    events = list(extract_from_outer(outer_filedb, title=title, items=items))

    progress("aggregating by item and route")
    item_rows, route_rows, overview, locale_keys = _build_aggregates_and_overview(
        save_path, title, events
    )

    progress("enumerating islands and routes")
    islands_by_session = _collect_islands_by_session(inner_payloads, overview.session_ids)
    routes_by_session = _collect_routes_by_session(inner_payloads, overview.session_ids)
    storage_by_island = _collect_storage_by_island(inner_payloads)

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
        routes_by_session=routes_by_session,
        storage_by_island=storage_by_island,
    )


def _load_inner_sessions(save_path: Path) -> list[bytes]:
    """save から内側 Session FileDB の bytes 列を取り出す (下位互換 API)．

    ``load_state`` 本体はもう使わず，outer を 1 度解凍して extract_sessions を
    直接呼ぶ．この関数はテストや外部呼び出し用に保持．
    """
    suffix = save_path.suffix.lower()
    if suffix in {".a7s", ".a8s"}:
        outer = extract_inner_filedb(save_path)
    else:
        raw = save_path.read_bytes()
        outer = zlib.decompress(raw) if raw[:2] in (b"\x78\x9c", b"\x78\xda", b"\x78\x01") else raw
    version = detect_version(outer)
    section = parse_tag_section(outer, version)
    return extract_sessions(outer, version=version, tag_section=section)


def _collect_islands_by_session(
    inner_payloads: list[bytes], session_ids: tuple[str, ...]
) -> dict[str, tuple[PlayerIsland, ...]]:
    """プリロード済 inner payloads からプレイヤー保有島を sid 別に列挙．"""
    if not session_ids:
        return {}
    by_extracted_sid = {str(i): inner for i, inner in enumerate(inner_payloads)}
    return {
        sid: list_player_islands(by_extracted_sid[sid])
        if sid.isdigit() and sid in by_extracted_sid
        else ()
        for sid in session_ids
    }


def _collect_routes_by_session(
    inner_payloads: list[bytes], session_ids: tuple[str, ...]
) -> dict[str, tuple[TradeRouteDef, ...]]:
    """プリロード済 inner payloads から定義済 TradeRoute を sid 別に列挙．"""
    if not session_ids:
        return {}
    by_extracted_sid = {str(i): inner for i, inner in enumerate(inner_payloads)}
    return {
        sid: list_trade_routes(by_extracted_sid[sid])
        if sid.isdigit() and sid in by_extracted_sid
        else ()
        for sid in session_ids
    }


def _collect_storage_by_island(
    inner_payloads: list[bytes],
) -> dict[str, tuple[IslandStorageTrend, ...]]:
    """プリロード済 inner payloads 横断で島別 StorageTrends を集める．

    島名 (CityName) は session 横断でユニーク前提．同名が別 session にあれば
    後勝ちになるが，書記長の実セーブで観測済の 13 島は全て unique．
    """
    aggregated: dict[str, list[IslandStorageTrend]] = {}
    for inner in inner_payloads:
        if not inner:
            continue
        for t in list_storage_trends(inner):
            aggregated.setdefault(t.island_name, []).append(t)
    return {name: tuple(items) for name, items in aggregated.items()}
