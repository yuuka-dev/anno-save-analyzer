"""DOM ストリーム走査．

FileDB の DOM セクションは ``[bytesize: int32][id: int32]`` の繰り返し．
id を signed int32 として解釈した上で以下の state を判定する:

- ``id >= 32768`` → Attrib．直後に ``bytesize`` バイト分の content が続く
  （V2/V3 は 8 バイト境界にパディングされる）．
- ``0 < id < 32768`` → Tag（子要素を持つ入れ子の開始）．
- ``id <= 0``        → Terminator（直近の Tag を閉じる）．

本モジュールは **streaming iterator** として設計し，巨大な 165MB 級 DOM を
O(chunk) メモリで消費できるようにする．
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum

from .dictionary import TagSection
from .exceptions import FileDBParseError
from .version import FileDBVersion

_MAX_ID = 0x8000  # 32768


class EventKind(Enum):
    """DOM イベントの種別．"""

    TAG = "tag"
    ATTRIB = "attrib"
    TERMINATOR = "terminator"


@dataclass(frozen=True)
class DomEvent:
    """DOM ストリーム中の 1 イベント．

    ``kind`` に応じて以下のフィールドを使い分ける:

    - TAG: ``id_`` （open）．``name`` は ``tag_section`` 指定時に解決される．
    - ATTRIB: ``id_`` / ``content`` （生バイト）．
    - TERMINATOR: 閉じイベント．``id_=0`` / ``content=b""``．
    """

    kind: EventKind
    id_: int
    name: str | None = None
    content: bytes = b""

    @property
    def is_tag(self) -> bool:
        return self.kind is EventKind.TAG

    @property
    def is_attrib(self) -> bool:
        return self.kind is EventKind.ATTRIB

    @property
    def is_terminator(self) -> bool:
        return self.kind is EventKind.TERMINATOR


# 後方互換的に `Tag` / `Attrib` / `Terminator` という簡易ファクトリも公開する．
def Tag(id_: int, name: str | None = None) -> DomEvent:
    return DomEvent(kind=EventKind.TAG, id_=id_, name=name)


def Attrib(id_: int, content: bytes, name: str | None = None) -> DomEvent:
    return DomEvent(kind=EventKind.ATTRIB, id_=id_, content=content, name=name)


def Terminator() -> DomEvent:
    return DomEvent(kind=EventKind.TERMINATOR, id_=0)


def _block_space(bytesize: int, block_size: int) -> int:
    """Attrib content を block アラインしたときのディスク上サイズ．"""
    if block_size <= 0:
        return bytesize
    if bytesize <= 0:
        return 0
    return ((bytesize + block_size - 1) // block_size) * block_size


def iter_dom(
    data: bytes | memoryview,
    version: FileDBVersion,
    *,
    tag_section: TagSection | None = None,
    dom_end: int | None = None,
) -> Iterator[DomEvent]:
    """DOM セクションを streaming で走査し ``DomEvent`` を yield する．

    ``dom_end`` を指定しないときは ``TagsOffset`` まで（= DOM の終端）を
    自動計算する．引数 ``data`` は全体バッファを想定．
    """
    n = len(data)
    if n < version.offset_to_offsets:
        raise FileDBParseError("buffer too small to hold DOM and tag section")

    if dom_end is None:
        # TagsOffset 位置を DOM の終端として用いる．
        ofs_start = n - version.offset_to_offsets
        dom_end = struct.unpack_from("<i", data, ofs_start)[0]
        if not (0 <= dom_end <= n):
            raise FileDBParseError(f"TagsOffset out of bounds: {dom_end}")

    block_size = version.block_size
    pos = 0
    depth = 0

    while pos < dom_end:
        if pos + 8 > dom_end:
            raise FileDBParseError(f"unexpected EOF in DOM header at pos={pos} (dom_end={dom_end})")
        bytesize, raw_id = struct.unpack_from("<iI", data, pos)
        pos += 8
        # signed int32 として解釈
        id_signed = struct.unpack("<i", struct.pack("<I", raw_id))[0]
        id16 = raw_id & 0xFFFF

        if id_signed <= 0:
            # Terminator: DOM の最後は depth=-1 に落ちる追加 terminator で終わる．
            yield Terminator()
            depth -= 1
            if depth < -1:
                raise FileDBParseError("more Terminators than opened Tags")
            continue

        if id16 >= _MAX_ID:
            # Attrib
            content_disk = _block_space(bytesize, block_size)
            if pos + content_disk > dom_end:
                raise FileDBParseError(
                    f"Attrib content extends past DOM end: pos={pos} "
                    f"need={content_disk} dom_end={dom_end}"
                )
            content = bytes(data[pos : pos + bytesize])
            pos += content_disk
            name = None
            if tag_section is not None:
                name = tag_section.attribs.get(id16)
            yield Attrib(id_=id16, content=content, name=name)
            continue

        # 残り: Tag（0 < id16 < 32768）
        name = None
        if tag_section is not None:
            name = tag_section.tags.get(id16)
        yield Tag(id_=id16, name=name)
        depth += 1
