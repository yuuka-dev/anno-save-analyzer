"""trade テスト用フィクスチャ．

合成 FileDB を組み立て，``PassiveTrade > History > {TradeRouteEntries,
PassiveTradeEntries} > <1> > <1> > TradedGoods`` の階層を持つ outer +
inner（再帰 FileDB）の最小ペアを作る．interpreter / extract / cli の
全テストはこの fixture をベースに走る．
"""

from __future__ import annotations

import struct
from typing import Literal

# tests/parser/filedb/conftest.py で既に組み立て済の helper を借りる
from tests.parser.filedb.conftest import (  # noqa: F401
    Event,
    FileDBFixture,
    encode_dictionary,
    encode_dom,
    minimal_v3,
)

ROUTE = "TradeRouteEntries"
PASSIVE = "PassiveTradeEntries"


def make_inner_filedb(
    triples_by_kind: dict[Literal["route", "passive"], list[tuple[int, int, int, int]]],
) -> bytes:
    """内側 FileDB V3 を組み立てる．

    triples_by_kind の値は ``[(trader, good_guid, amount, total_price), ...]`` のリスト．
    `trader` は外側 ``<1>`` ラッパに ``Trader`` attrib として乗せる route_id /
    partner_id．
    """
    # tag id 割り当て
    tags: dict[int, str] = {
        2: "PassiveTrade",
        3: "History",
        4: ROUTE,
        5: PASSIVE,
        6: "TradedGoods",
        # 匿名コレクション要素（内部 <1>）は id=1 だが辞書に登録しない
    }
    attribs: dict[int, str] = {
        0x8001: "Trader",
        0x8002: "GoodGuid",
        0x8003: "GoodAmount",
        0x8004: "TotalPrice",
    }

    events: list[Event] = []
    events.append(("T", 2))  # PassiveTrade
    events.append(("T", 3))  # History
    for kind in ("route", "passive"):
        if kind not in triples_by_kind:
            continue
        events.append(("T", 4 if kind == "route" else 5))  # TradeRouteEntries / PassiveTradeEntries
        # 各 trader ごとに外側 <1> を 1 個作る．trader を attrib に持たせる．
        # シンプルに 1 trader = 1 outer <1> = N inner <1> (= N triples)
        triples_for_kind = triples_by_kind[kind]
        # group by trader id
        traders: dict[int, list[tuple[int, int, int, int]]] = {}
        for entry in triples_for_kind:
            traders.setdefault(entry[0], []).append(entry)
        for _trader, group in traders.items():
            events.append(("T", 1))  # 外側 <1>
            for trader_, good, amount, price in group:
                events.append(("T", 1))  # 内側 <1>
                events.append(("A", 0x8001, struct.pack("<i", trader_)))  # Trader
                events.append(("T", 6))  # TradedGoods
                # TradedGoods 直下にもう一段の <1> ラッパに GoodGuid/Amount/Price
                events.append(("T", 1))
                events.append(("A", 0x8002, struct.pack("<i", good)))
                events.append(("A", 0x8003, struct.pack("<i", amount)))
                events.append(("A", 0x8004, struct.pack("<i", price)))
                events.append(("X",))  # close inner <1> within TradedGoods
                events.append(("X",))  # close TradedGoods
                events.append(("X",))  # close inner <1> (entry)
            events.append(("X",))  # close outer <1>
        events.append(("X",))  # close TradeRouteEntries / PassiveTradeEntries
    events.append(("X",))  # close History
    events.append(("X",))  # close PassiveTrade

    return minimal_v3(tags=tags, attribs=attribs, events=events)


def wrap_as_outer(inner_payloads: list[bytes]) -> bytes:
    """SessionData > BinaryData の階層に inner FileDB を埋め込んだ outer FileDB を作る．"""
    tags = {1: "SessionData"}
    attribs = {0x8001: "BinaryData"}
    events: list[Event] = []
    for inner in inner_payloads:
        events.append(("T", 1))  # SessionData
        events.append(("A", 0x8001, inner))
        events.append(("X",))  # close SessionData
    return minimal_v3(tags=tags, attribs=attribs, events=events)


def make_save_file(inner_payloads: list[bytes]) -> bytes:
    """outer FileDB をそのまま `.bin` 風 raw として返す．

    ``trade.extract.extract`` は ``.a7s`` / ``.a8s`` 拡張子で zlib 経由を
    試みるが，それ以外では bare bytes を直接読むため，テストでは ``.bin``
    などの拡張子で書き出してこの payload を渡す．
    """
    return wrap_as_outer(inner_payloads)
