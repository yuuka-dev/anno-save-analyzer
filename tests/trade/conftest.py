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
    *,
    include_npc_island: bool = False,
) -> bytes:
    """内側 FileDB V3 を組み立てる．

    ``triples_by_kind`` の値は ``[(trader, good_guid, amount, total_price), ...]`` のリスト．
    生成される DOM は ``GameSessionManager > AreaInfo > <1> > PassiveTrade > History
    > {TradeRouteEntries|PassiveTradeEntries} > <1> > <1> > TradedGoods > <1>``
    の階層を持ち，``AreaInfo > <1>`` 直下に ``CityName`` attrib を置くことで
    プレイヤー保有島として扱われる．

    ``include_npc_island=True`` の場合，さらに ``CityName`` を持たない 2 つ目の
    AreaInfo entry を追加し，その中にも同じ TradedGoods 構造を入れる．
    interpreter は NPC 島の TradedGoods を skip すべき．
    """
    # tag id 割り当て
    tags: dict[int, str] = {
        2: "PassiveTrade",
        3: "History",
        4: ROUTE,
        5: PASSIVE,
        6: "TradedGoods",
        7: "AreaInfo",
        # 匿名コレクション要素（内部 <1>）は id=1 だが辞書に登録しない
    }
    attribs: dict[int, str] = {
        0x8001: "Trader",
        0x8002: "GoodGuid",
        0x8003: "GoodAmount",
        0x8004: "TotalPrice",
        0x8005: "CityName",
        0x8006: "RouteID",
    }

    def _trade_subtree() -> list[Event]:
        sub: list[Event] = []
        sub.append(("T", 2))  # PassiveTrade
        sub.append(("T", 3))  # History
        for kind in ("route", "passive"):
            if kind not in triples_by_kind:
                continue
            sub.append(("T", 4 if kind == "route" else 5))
            traders: dict[int, list[tuple[int, int, int, int]]] = {}
            for entry in triples_by_kind[kind]:
                traders.setdefault(entry[0], []).append(entry)
            for _trader, group in traders.items():
                sub.append(("T", 1))  # 外側 <1>
                for trader_, good, amount, price in group:
                    sub.append(("T", 1))  # 内側 <1>
                    # route は RouteID (0x8006) / passive は Trader (0x8001) を使う．
                    # 実セーブの inner entry 構造に合わせる (interpreter の文脈分岐で必要)．
                    ident_attrib = 0x8006 if kind == "route" else 0x8001
                    sub.append(("A", ident_attrib, struct.pack("<i", trader_)))
                    sub.append(("T", 6))  # TradedGoods
                    sub.append(("T", 1))  # depth=1 wrapper
                    sub.append(("A", 0x8002, struct.pack("<i", good)))
                    sub.append(("A", 0x8003, struct.pack("<i", amount)))
                    sub.append(("A", 0x8004, struct.pack("<i", price)))
                    sub.append(("X",))  # close depth=1 wrapper
                    sub.append(("X",))  # close TradedGoods
                    sub.append(("X",))  # close inner <1> (entry)
                sub.append(("X",))  # close outer <1>
            sub.append(("X",))  # close TradeRouteEntries / PassiveTradeEntries
        sub.append(("X",))  # close History
        sub.append(("X",))  # close PassiveTrade
        return sub

    events: list[Event] = []
    events.append(("T", 7))  # AreaInfo

    # プレイヤー保有島の entry
    events.append(("T", 1))  # AreaInfo > <1>
    events.append(("A", 0x8005, "プレイヤー島".encode("utf-16-le")))  # CityName
    events.extend(_trade_subtree())
    events.append(("X",))  # close AreaInfo > <1>

    if include_npc_island:
        # NPC 島の entry．CityName 無し，同じ trade 構造．フィルタで除外されるはず．
        events.append(("T", 1))  # AreaInfo > <1>
        events.extend(_trade_subtree())
        events.append(("X",))  # close NPC entry

    events.append(("X",))  # close AreaInfo

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
