"""raw triple → TradeEvent 正規化と save → ledger 抽出のオーケストレーション．"""

from __future__ import annotations

import zlib
from collections.abc import Iterator
from pathlib import Path

from anno_save_analyzer.parser.filedb import (
    detect_version,
    parse_tag_section,
)
from anno_save_analyzer.parser.pipeline import extract_inner_filedb

from .interpreter import GameInterpreter, select_interpreter
from .interpreter.base import RawTradedGoodTriple
from .items import ItemDictionary
from .models import GameTitle, TradeEvent, TradingPartner


def normalise(
    raw: RawTradedGoodTriple,
    items: ItemDictionary,
) -> TradeEvent:
    """1 件の raw triple を TradeEvent に組み立てる．

    Anno 117 では「Trader」attrib が文脈で意味を変えるため，interpreter は
    route_id / partner_id を排他で埋める．本関数は両方の場合に対して
    ``TradingPartner`` を必ず生成し，集計層で kind が常に確定するようにする．
    """
    item = items[raw.good_guid]
    partner: TradingPartner | None = None
    if raw.context.partner_id is not None:
        partner = TradingPartner(
            id=raw.context.partner_id,
            display_name=raw.context.partner_id,
            kind=raw.context.partner_kind,
        )
    elif raw.context.route_id is not None:
        partner = TradingPartner(
            id=f"route:{raw.context.route_id}",
            display_name=f"Route #{raw.context.route_id}",
            kind=raw.context.partner_kind,
        )
    return TradeEvent(
        timestamp_tick=raw.context.timestamp_tick,
        item=item,
        amount=raw.amount,
        total_price=raw.total_price,
        partner=partner,
        route_id=raw.context.route_id,
        session_id=raw.context.session_id,
        island_name=raw.context.island_name,
        source_method="history",
    )


def extract(
    save_path: str | Path,
    *,
    title: GameTitle,
    items: ItemDictionary,
    interpreter: GameInterpreter | None = None,
) -> Iterator[TradeEvent]:
    """``.a7s`` / ``.a8s`` セーブから TradeEvent ストリームを yield する．"""
    outer_filedb = load_outer_filedb(Path(save_path))
    yield from extract_from_outer(outer_filedb, title=title, items=items, interpreter=interpreter)


def extract_from_outer(
    outer_filedb: bytes,
    *,
    title: GameTitle,
    items: ItemDictionary,
    interpreter: GameInterpreter | None = None,
) -> Iterator[TradeEvent]:
    """既に解凍済みの outer FileDB bytes から TradeEvent ストリームを yield．

    TUI のロードパスでは outer を 1 回だけ解凍して使い回すために使う
    (``extract`` が内部で毎回 ``extract_inner_filedb`` を呼ぶと RDA + zlib
    を重複実行する)．
    """
    interpreter = interpreter or select_interpreter(title)
    version = detect_version(outer_filedb)
    section = parse_tag_section(outer_filedb, version)
    for raw in interpreter.find_traded_goods(outer_filedb, section):
        yield normalise(raw, items)


def load_outer_filedb(save_path: Path) -> bytes:
    """``.a7s`` / ``.a8s`` を解凍して内部 FileDB バイナリを返す．

    bare FileDB バイナリ (テスト用 ``.bin``) も自動判定．zlib 圧縮済なら展開．
    """
    suffix = save_path.suffix.lower()
    if suffix in {".a7s", ".a8s"}:
        return extract_inner_filedb(save_path)
    raw = save_path.read_bytes()
    if raw[:2] in (b"\x78\x9c", b"\x78\xda", b"\x78\x01"):
        return zlib.decompress(raw)
    return raw
