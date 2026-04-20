"""貿易ルート定義の列挙．

Anno 117 の内側 Session FileDB には，`ConstructionAI > TradeRoute > TradeRoutes > <1>`
配下に定義済み貿易ルートが列挙されている．Trade history (`TradeRouteEntries`) に
まだ履歴が出てない idle route もここから拾えるため，「登録済全ルート ∖ 履歴あり ルート」
で idle を特定できる．

本モジュールは title-agnostic な生抽出のみ行う．semantic な解釈 (idle 判定など) は
呼び出し側．
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass

from anno_save_analyzer.parser.filedb import (
    EventKind,
    FileDBVersion,
    TagSection,
    detect_version,
    iter_dom,
    parse_tag_section,
)

_CONSTRUCTION_AI_TAG = "ConstructionAI"
_TRADE_ROUTE_TAG = "TradeRoute"
_TRADE_ROUTES_TAG = "TradeRoutes"
_TRANSPORT_TASKS_TAG = "TransportTasks"

_ROUTE_ATTRIB = "Route"
_SHIP_ID_ATTRIB = "ShipID"
_ROUND_TRAVEL_ATTRIB = "RoundTravel"
_ESTABLISH_TIME_ATTRIB = "EstablishTime"

_FROM_ATTRIB = "From"
_TO_ATTRIB = "To"
_PRODUCT_ATTRIB = "Product"
_BALANCE_ATTRIB = "Balance"


@dataclass(frozen=True)
class TransportTask:
    """TradeRoute 配下の 1 レグ．

    ``from_key`` / ``to_key`` は save 内部の u16 キー (建物 / dock の localID と推定)．
    AreaManager_<N> / CityName への対応は未解明．
    """

    from_key: int
    to_key: int
    product_guid: int
    balance_raw: int


@dataclass(frozen=True)
class TradeRouteDef:
    """貿易ルート 1 本．

    ``ship_id`` は trade history の ``Trader`` attrib と一致するため，履歴との
    突き合わせ (idle 判定) に使える．``route_hash`` は Anno 内部のルート識別子．
    """

    ship_id: int | None
    route_hash: int | None
    round_travel: int | None
    establish_time: int | None
    tasks: tuple[TransportTask, ...]


def list_trade_routes(inner_session: bytes) -> tuple[TradeRouteDef, ...]:
    """内側 Session FileDB から登録済貿易ルートを全件抽出．

    複数 ``ConstructionAI`` ブロックがある場合 (プレイヤー + AI) はそれぞれ展開し，
    呼び出し側が必要に応じて ship_id などで filter する．
    """
    if not inner_session:
        return ()
    version = detect_version(inner_session)
    section = parse_tag_section(inner_session, version)
    tag_ids = _resolve_tag_ids(section)
    if tag_ids is None:
        return ()
    return tuple(_iter_routes(inner_session, version, section, tag_ids))


def _resolve_tag_ids(section: TagSection) -> tuple[int, int, int, int | None] | None:
    def find(name: str) -> int | None:
        return next(
            (tid for tid, n in section.tags.entries.items() if n == name),
            None,
        )

    ca_id = find(_CONSTRUCTION_AI_TAG)
    tr_id = find(_TRADE_ROUTE_TAG)
    trs_id = find(_TRADE_ROUTES_TAG)
    tt_id = find(_TRANSPORT_TASKS_TAG)
    if ca_id is None or tr_id is None or trs_id is None:
        return None
    return ca_id, tr_id, trs_id, tt_id


def _iter_routes(
    inner: bytes,
    version: FileDBVersion,
    section: TagSection,
    tag_ids: tuple[int, int, int, int | None],
) -> Iterator[TradeRouteDef]:
    ca_id, tr_id, trs_id, tt_id = tag_ids

    stack: list[int] = []
    in_ca_depth: int | None = None
    in_tr_depth: int | None = None
    in_trs_depth: int | None = None
    in_route_depth: int | None = None
    in_tt_depth: int | None = None
    in_task_depth: int | None = None

    route_bucket: dict[str, int] = {}
    task_bucket: dict[str, int] = {}
    tasks: list[TransportTask] = []

    for ev in iter_dom(inner, version, tag_section=section):
        if ev.kind is EventKind.TAG:
            stack.append(ev.id_)
            depth = len(stack)
            if ev.id_ == ca_id and in_ca_depth is None:
                in_ca_depth = depth
            elif ev.id_ == tr_id and in_ca_depth is not None and in_tr_depth is None:
                in_tr_depth = depth
            elif ev.id_ == trs_id and in_tr_depth is not None and in_trs_depth is None:
                in_trs_depth = depth
            elif in_trs_depth is not None and in_route_depth is None and depth == in_trs_depth + 1:
                in_route_depth = depth
                route_bucket = {}
                tasks = []
            elif (
                tt_id is not None
                and ev.id_ == tt_id
                and in_route_depth is not None
                and in_tt_depth is None
            ):
                in_tt_depth = depth
            elif in_tt_depth is not None and in_task_depth is None and depth == in_tt_depth + 1:
                in_task_depth = depth
                task_bucket = {}
            continue

        if ev.kind is EventKind.ATTRIB:
            if in_task_depth is not None and len(stack) == in_task_depth:
                _capture_task_attrib(task_bucket, ev.name, ev.content)
            elif in_route_depth is not None and len(stack) == in_route_depth:
                _capture_route_attrib(route_bucket, ev.name, ev.content)
            continue

        # Terminator
        if not stack:
            continue
        closing_depth = len(stack)
        if in_task_depth is not None and closing_depth == in_task_depth:
            task = _build_task(task_bucket)
            if task is not None:
                tasks.append(task)
            in_task_depth = None
        elif in_tt_depth is not None and closing_depth == in_tt_depth:
            in_tt_depth = None
        elif in_route_depth is not None and closing_depth == in_route_depth:
            yield _build_route(route_bucket, tuple(tasks))
            in_route_depth = None
        elif in_trs_depth is not None and closing_depth == in_trs_depth:
            in_trs_depth = None
        elif in_tr_depth is not None and closing_depth == in_tr_depth:
            in_tr_depth = None
        elif in_ca_depth is not None and closing_depth == in_ca_depth:
            in_ca_depth = None
        stack.pop()


def _capture_route_attrib(bucket: dict[str, int], name: str | None, content: bytes) -> None:
    if name == _ROUTE_ATTRIB:
        value = _as_i32(content)
        if value is not None:
            bucket["route_hash"] = value
    elif name == _SHIP_ID_ATTRIB:
        value = _as_i32(content)
        if value is not None:
            bucket["ship_id"] = value
    elif name == _ROUND_TRAVEL_ATTRIB:
        value = _as_i64(content)
        if value is not None:
            bucket["round_travel"] = value
    elif name == _ESTABLISH_TIME_ATTRIB:
        value = _as_i64(content)
        if value is not None:
            bucket["establish_time"] = value


def _capture_task_attrib(bucket: dict[str, int], name: str | None, content: bytes) -> None:
    if name == _FROM_ATTRIB:
        value = _as_u16(content)
        if value is not None:
            bucket["from_key"] = value
    elif name == _TO_ATTRIB:
        value = _as_u16(content)
        if value is not None:
            bucket["to_key"] = value
    elif name == _PRODUCT_ATTRIB:
        value = _as_i32(content)
        if value is not None:
            bucket["product_guid"] = value
    elif name == _BALANCE_ATTRIB:
        value = _as_i32(content)
        if value is not None:
            bucket["balance_raw"] = value


def _build_task(bucket: dict[str, int]) -> TransportTask | None:
    if "from_key" not in bucket or "to_key" not in bucket or "product_guid" not in bucket:
        return None
    return TransportTask(
        from_key=bucket["from_key"],
        to_key=bucket["to_key"],
        product_guid=bucket["product_guid"],
        balance_raw=bucket.get("balance_raw", 0),
    )


def _build_route(bucket: dict[str, int], tasks: tuple[TransportTask, ...]) -> TradeRouteDef:
    return TradeRouteDef(
        ship_id=bucket.get("ship_id"),
        route_hash=bucket.get("route_hash"),
        round_travel=bucket.get("round_travel"),
        establish_time=bucket.get("establish_time"),
        tasks=tasks,
    )


def _as_i32(buf: bytes) -> int | None:
    if len(buf) >= 4:
        return struct.unpack_from("<i", buf, 0)[0]
    return None


def _as_i64(buf: bytes) -> int | None:
    if len(buf) >= 8:
        return struct.unpack_from("<q", buf, 0)[0]
    return None


def _as_u16(buf: bytes) -> int | None:
    if len(buf) >= 2:
        return struct.unpack_from("<H", buf, 0)[0]
    return None
