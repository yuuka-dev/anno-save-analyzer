"""Anno 117 (Pax Romana) interpreter．

W-1 spike (rev 5 / Appendix B) で確定した抽出規則:

- 内側 Session FileDB の DOM を walk
- ``PassiveTrade > History > TradeRouteEntries > <1> > <1> > TradedGoods`` または
  ``PassiveTrade > History > PassiveTradeEntries > <1> > <1> > TradedGoods`` 配下
  だけを valid な親と認識
- それ以外（``ConstructionAI > EventBuffer`` 等）は skip
- 外側 ``<1>`` の attrib（``RouteID`` / ``TraderGUID`` 等）を route_id / partner_id に
- 内側 ``<1>`` の attrib（タイムスタンプ）を timestamp_tick に
"""

from __future__ import annotations

import struct
from collections.abc import Iterator

from anno_save_analyzer.parser.filedb import (
    EventKind,
    TagSection,
    detect_version,
    extract_sessions,
    iter_dom,
    parse_tag_section,
)

from ..models import GameTitle, PartnerKind
from .base import ExtractionContext, GameInterpreter, RawTradedGoodTriple

_HISTORY_PARENT_TAG = "History"
_PASSIVE_TRADE_ROOT_TAG = "PassiveTrade"
_TRADE_ROUTE_ENTRIES = "TradeRouteEntries"
_PASSIVE_TRADE_ENTRIES = "PassiveTradeEntries"
_TRADED_GOODS_TAG = "TradedGoods"

# 親階層の attrib name 候補．実測（rev 5 W-1 spike + 続報）に基づく．
# Anno 117 では `Trader` という同名 attrib が文脈によって意味を変える：
# - TradeRouteEntries 配下 → route_id（プレイヤー所有 route の internal ID）
# - PassiveTradeEntries 配下 → partner_id（NPC trader の GUID）
_TRADER_ATTRIB = "Trader"
_TIMESTAMP_ATTRIB_CANDIDATES = (
    "LastGoodTradeUpdate",
    "Timestamp",
    "TradeTime",
    "Tick",
)


class Anno117Interpreter(GameInterpreter):
    """Anno 117 用 trade extractor．"""

    title = GameTitle.ANNO_117

    def find_traded_goods(
        self,
        outer_filedb: bytes,
        outer_section: TagSection,
    ) -> Iterator[RawTradedGoodTriple]:
        outer_version = detect_version(outer_filedb)
        sessions = extract_sessions(outer_filedb, version=outer_version, tag_section=outer_section)
        for session_idx, inner in enumerate(sessions):
            if not inner:
                continue
            yield from _walk_inner_session(inner, session_idx)


def _walk_inner_session(inner: bytes, session_idx: int) -> Iterator[RawTradedGoodTriple]:
    inner_version = detect_version(inner)
    inner_section = parse_tag_section(inner, inner_version)

    # tag stack（名前ベース）
    tag_stack: list[str] = []
    # 各 <1> ラッパで集めた attrib（route_id / partner / timestamp 用）
    # 階層ごとに dict のスタックを持つ
    attrib_stack: list[dict[str, bytes]] = []

    # TradedGoods 内部の集計用
    in_traded_goods = False
    traded_goods_depth = 0
    current_triple: dict[str, int | None] = _empty_triple()
    pending_kind: PartnerKind = "unknown"

    session_id = str(session_idx)

    for ev in iter_dom(inner, inner_version, tag_section=inner_section):
        if ev.kind is EventKind.TAG:
            name = ev.name or f"<{ev.id_}>"
            tag_stack.append(name)
            attrib_stack.append({})

            if name == _TRADED_GOODS_TAG:
                kind = _classify_parent(tag_stack)
                if kind is None:
                    # 想定外 (ConstructionAI/EventBuffer 等) は skip
                    continue
                in_traded_goods = True
                traded_goods_depth = 0
                pending_kind = kind
            elif in_traded_goods:
                traded_goods_depth += 1
                if traded_goods_depth == 1:
                    current_triple = _empty_triple()
            continue

        if ev.kind is EventKind.ATTRIB:
            # FileDB DOM は root レベルにも attrib を持ちうる（例: SessionFileVersion）．
            # その場合 attrib_stack は空のためガードする．
            if attrib_stack:
                attrib_stack[-1][ev.name or f"<{ev.id_}>"] = ev.content

            if in_traded_goods and traded_goods_depth >= 1:
                # TradedGoods 直下の child (<1>) 配下に GoodGuid / GoodAmount / TotalPrice
                attr_name = ev.name
                if attr_name == "GoodGuid":
                    current_triple["good_guid"] = _read_int32(ev.content)
                elif attr_name == "GoodAmount":
                    current_triple["amount"] = _read_int32(ev.content)
                elif attr_name == "TotalPrice":
                    current_triple["total_price"] = _read_int32(ev.content)
            continue

        # Terminator．DOM の終端で root より先に出る余分な terminator は
        # `iter_dom` 側で正規化されているはずだが，安全のためガード付きで pop．
        if not tag_stack:
            continue
        closing_name = tag_stack.pop()
        attrib_stack.pop()

        if in_traded_goods and closing_name != _TRADED_GOODS_TAG:
            if traded_goods_depth == 1:
                triple = _build_triple_if_complete(
                    current_triple,
                    session_id=session_id,
                    kind=pending_kind,
                    ancestor_attribs=attrib_stack,
                )
                if triple is not None:
                    yield triple
            traded_goods_depth -= 1
            continue

        if closing_name == _TRADED_GOODS_TAG and in_traded_goods:
            in_traded_goods = False
            traded_goods_depth = 0


def _empty_triple() -> dict[str, int | None]:
    return {"good_guid": None, "amount": None, "total_price": None}


def _classify_parent(tag_stack: list[str]) -> PartnerKind | None:
    """直前 tag stack から TradedGoods の親種別を判定．有効な親なら kind を返す．"""
    # 想定 stack 例:
    # [..., "PassiveTrade", "History", "TradeRouteEntries", "<1>", "<1>", "TradedGoods"]
    # この時点では "TradedGoods" はまだ stack に積まれてない（ev は OPEN，先に append）．
    # ただし上の処理順では append 後に分類してる．
    # tag_stack[-1] が TradedGoods．その上 5 階層を見る．
    if len(tag_stack) < 6:
        return None
    ancestors = tag_stack[-6:-1]  # TradedGoods の直近 5 個の祖先
    if (
        ancestors[0] == _PASSIVE_TRADE_ROOT_TAG
        and ancestors[1] == _HISTORY_PARENT_TAG
        and ancestors[2] in (_TRADE_ROUTE_ENTRIES, _PASSIVE_TRADE_ENTRIES)
    ):
        return "route" if ancestors[2] == _TRADE_ROUTE_ENTRIES else "passive"
    return None


def _build_triple_if_complete(
    triple: dict[str, int | None],
    *,
    session_id: str,
    kind: PartnerKind,
    ancestor_attribs: list[dict[str, bytes]],
) -> RawTradedGoodTriple | None:
    if triple["good_guid"] is None or triple["amount"] is None:
        return None
    total_price = triple["total_price"] or 0

    # ``Trader`` attrib を親階層から拾う．文脈で意味が変わる（前述コメント）．
    trader_value = _first_int32_attrib(ancestor_attribs, (_TRADER_ATTRIB,))
    timestamp_tick = _first_int_attrib(ancestor_attribs, _TIMESTAMP_ATTRIB_CANDIDATES)

    route_id: str | None = None
    partner_id: str | None = None
    if trader_value is not None:
        as_str = str(trader_value)
        if kind == "route":
            route_id = as_str
        elif kind == "passive":
            partner_id = as_str

    return RawTradedGoodTriple(
        good_guid=int(triple["good_guid"]),
        amount=int(triple["amount"]),
        total_price=int(total_price),
        context=ExtractionContext(
            session_id=session_id,
            route_id=route_id,
            partner_id=partner_id,
            partner_kind=kind,
            timestamp_tick=timestamp_tick,
        ),
    )


def _first_int32_attrib(
    attrib_stack: list[dict[str, bytes]], candidates: tuple[str, ...]
) -> int | None:
    for attribs in reversed(attrib_stack):
        for candidate in candidates:
            if candidate in attribs:
                value = attribs[candidate]
                if len(value) >= 4:
                    return _read_int32(value)
    return None


def _first_int_attrib(
    attrib_stack: list[dict[str, bytes]], candidates: tuple[str, ...]
) -> int | None:
    for attribs in reversed(attrib_stack):
        for candidate in candidates:
            if candidate in attribs:
                value = attribs[candidate]
                if len(value) == 8:
                    return _read_int64(value)
                if len(value) == 4:
                    return _read_int32(value)
    return None


def _read_int32(buf: bytes) -> int:
    if len(buf) < 4:
        return 0
    return struct.unpack_from("<i", buf, 0)[0]


def _read_int64(buf: bytes) -> int:
    if len(buf) < 8:
        return 0
    return struct.unpack_from("<q", buf, 0)[0]
