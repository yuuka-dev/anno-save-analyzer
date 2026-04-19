"""FileDB テスト用のフィクスチャビルダ．

V2 / V3 の最小 FileDB バイト列を手続き的に組み立てるユーティリティ．
境界系の破壊的パラメータも受け付け，壊れた入力で error path を踏ませる．
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Literal

from anno_save_analyzer.parser.filedb.version import (
    _MAGIC_V2,
    _MAGIC_V3,
    FileDBVersion,
)

AttribEvent = tuple[Literal["A"], int, bytes]  # (kind, id, content)
TagEvent = tuple[Literal["T"], int]  # (kind, id)
TermEvent = tuple[Literal["X"]]  # terminator
Event = AttribEvent | TagEvent | TermEvent


def _block_pad(content: bytes, block_size: int) -> bytes:
    """Attrib content を block 境界まで 0 パディング．"""
    if block_size <= 0 or len(content) == 0:
        return content
    padding = (-len(content)) % block_size
    return content + b"\x00" * padding


def encode_dom(events: list[Event], block_size: int) -> bytes:
    """イベント列を FileDB DOM バイト列にエンコード．"""
    out = bytearray()
    for ev in events:
        if ev[0] == "A":
            _, id_, content = ev
            out += struct.pack("<iI", len(content), id_)
            out += _block_pad(content, block_size)
        elif ev[0] == "T":
            _, id_ = ev
            out += struct.pack("<iI", 0, id_)
        else:  # "X" terminator
            out += struct.pack("<iI", 0, 0)
    return bytes(out)


def encode_dictionary(mapping: dict[int, str]) -> bytes:
    """V2/V3 辞書 ``[Count:i32][IDs:u16×N][Names:UTF-8 0x00]`` をエンコード．"""
    ids = list(mapping.keys())
    count = len(ids)
    out = bytearray()
    out += struct.pack("<i", count)
    for tid in ids:
        out += struct.pack("<H", tid)
    for tid in ids:
        out += mapping[tid].encode("utf-8") + b"\x00"
    return bytes(out)


@dataclass
class FileDBFixture:
    """FileDB V2/V3 1 本分を構築するスペック．"""

    version: FileDBVersion = FileDBVersion.V3
    tags: dict[int, str] = field(default_factory=dict)
    attribs: dict[int, str] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)

    # 境界試験用の override フック
    override_tag_offset: int | None = None
    override_attrib_offset: int | None = None
    override_magic: bytes | None = None

    def build(self) -> bytes:
        block_size = self.version.block_size
        dom = encode_dom(self.events, block_size)
        tag_dict_bytes = encode_dictionary(self.tags)
        attrib_dict_bytes = encode_dictionary(self.attribs)

        tags_offset = len(dom)
        attribs_offset = tags_offset + len(tag_dict_bytes)
        if self.override_tag_offset is not None:
            tags_offset = self.override_tag_offset
        if self.override_attrib_offset is not None:
            attribs_offset = self.override_attrib_offset

        out = bytearray()
        out += dom
        out += tag_dict_bytes
        out += attrib_dict_bytes
        out += struct.pack("<ii", tags_offset, attribs_offset)
        magic = self.override_magic
        if magic is None:
            magic = _MAGIC_V3 if self.version is FileDBVersion.V3 else _MAGIC_V2
        out += magic
        return bytes(out)


def minimal_v3(tags: dict[int, str], attribs: dict[int, str], events: list[Event]) -> bytes:
    """V3 最小 FileDB を合成．"""
    return FileDBFixture(
        version=FileDBVersion.V3, tags=tags, attribs=attribs, events=events
    ).build()
