"""Tag / Attrib 名の辞書 decode．

V2 / V3 の辞書フォーマット（``ParseDictionary`` 参照）::

    [Count: int32 LE]
    [ID_0: uint16 LE]
    [ID_1: uint16 LE]
    ...
    [Name_0: UTF-8 null-terminated]
    [Name_1: UTF-8 null-terminated]
    ...

末尾には offset ペア（TagsOffset, AttribsOffset）があり，そこから辞書開始位置を得る．
V1 は offset ペア 1 個のみ．
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .exceptions import FileDBParseError, UnsupportedFileDBVersion
from .version import FileDBVersion


@dataclass(frozen=True)
class TagDictionary:
    """ID → 名前 の辞書．Tag 用と Attrib 用で別インスタンスを作る．"""

    entries: dict[int, str]

    def __contains__(self, key: int) -> bool:
        return key in self.entries

    def __getitem__(self, key: int) -> str:
        return self.entries[key]

    def get(self, key: int, default: str | None = None) -> str | None:
        return self.entries.get(key, default)

    def __len__(self) -> int:
        return len(self.entries)


@dataclass(frozen=True)
class TagSection:
    """FileDB ドキュメント 1 本分の tag / attrib 辞書ペア．"""

    tags: TagDictionary
    attribs: TagDictionary


def _parse_dictionary(data: bytes | memoryview, base: int) -> TagDictionary:
    """``base`` 位置から 1 辞書分を decode する．"""
    n = len(data)
    if base < 0 or base + 4 > n:
        raise FileDBParseError(f"dictionary offset out of range: base={base}")
    count = struct.unpack_from("<i", data, base)[0]
    if count < 0:
        raise FileDBParseError(f"negative dictionary count: {count}")

    ids_start = base + 4
    ids_end = ids_start + 2 * count
    if ids_end > n:
        raise FileDBParseError("dictionary IDs extend past EOF")

    ids: list[int] = [struct.unpack_from("<H", data, ids_start + 2 * i)[0] for i in range(count)]

    pos = ids_end
    entries: dict[int, str] = {}
    for tid in ids:
        try:
            end = data.index(b"\x00", pos)
        except ValueError as e:
            raise FileDBParseError(f"dictionary name at pos={pos} is not null-terminated") from e
        entries[tid] = bytes(data[pos:end]).decode("utf-8", errors="replace")
        pos = end + 1
    return TagDictionary(entries=entries)


def parse_tag_section(data: bytes | memoryview, version: FileDBVersion) -> TagSection:
    """末尾の offset ペアから tag / attrib 辞書を decode する．

    V1 は attrib 辞書を持たない形式のためサポート外．
    """
    if version is FileDBVersion.V1:
        raise UnsupportedFileDBVersion("FileDB V1 tag section layout is not supported in v0.2")

    n = len(data)
    offset_to_offsets = version.offset_to_offsets  # V2/V3 = 16
    if n < offset_to_offsets:
        raise FileDBParseError(
            f"buffer too small for tag section (len={n}, need >= {offset_to_offsets})"
        )
    # offset block は末尾 magic の直前，計 2 * int32 = 8B．
    ofs_start = n - offset_to_offsets
    tags_offset = struct.unpack_from("<i", data, ofs_start)[0]
    attribs_offset = struct.unpack_from("<i", data, ofs_start + 4)[0]

    tags = _parse_dictionary(data, tags_offset)
    attribs = _parse_dictionary(data, attribs_offset)
    return TagSection(tags=tags, attribs=attribs)
