"""RDA FileHeader および Version 定義．

バージョンごとに magic encoding, unknown 領域サイズ, UInt サイズが変わる．
V2.0 は UTF-16LE + uint32, V2.2 は UTF-8 + uint64 という対応関係．
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import Enum
from typing import BinaryIO

from .exceptions import RDAParseError, UnsupportedVersionError


class RDAVersion(Enum):
    """RDA コンテナのバージョン．本実装では V2_2 のみ完全対応．"""

    V2_0 = "2.0"
    V2_2 = "2.2"


_MAGIC_STRINGS: dict[RDAVersion, str] = {
    RDAVersion.V2_0: "Resource File V2.0",
    RDAVersion.V2_2: "Resource File V2.2",
}

_MAGIC_ENCODINGS: dict[RDAVersion, str] = {
    RDAVersion.V2_0: "utf-16-le",
    RDAVersion.V2_2: "utf-8",
}

_UNKNOWN_SIZES: dict[RDAVersion, int] = {
    RDAVersion.V2_0: 1008,
    RDAVersion.V2_2: 766,
}

_UINT_SIZES: dict[RDAVersion, int] = {
    RDAVersion.V2_0: 4,
    RDAVersion.V2_2: 8,
}


def magic_bytes(version: RDAVersion) -> bytes:
    """指定バージョンの magic バイト列を返す．"""
    return _MAGIC_STRINGS[version].encode(_MAGIC_ENCODINGS[version])


def uint_size(version: RDAVersion) -> int:
    """指定バージョンの可変 UInt サイズ（バイト）を返す．V2.0=4, V2.2=8．"""
    return _UINT_SIZES[version]


def read_uint(stream: BinaryIO, version: RDAVersion) -> int:
    """version に応じた LE uint32/uint64 を読み取る．"""
    size = uint_size(version)
    data = stream.read(size)
    if len(data) != size:
        raise RDAParseError(
            f"unexpected EOF while reading uint (got {len(data)}B, want {size}B)"
        )
    fmt = "<I" if size == 4 else "<Q"
    return struct.unpack(fmt, data)[0]


def detect_version(first_two_bytes: bytes) -> RDAVersion:
    """ファイル先頭 2 バイトからバージョンを推定する．

    - ``R\\x00`` → V2.0 (UTF-16LE で ``R`` の先頭 2B)
    - ``Re``     → V2.2 (UTF-8 で ``Re``)
    """
    if len(first_two_bytes) < 2:
        raise RDAParseError("file too small to detect RDA version")
    if first_two_bytes[0:2] == b"R\x00":
        return RDAVersion.V2_0
    if first_two_bytes[0:2] == b"Re":
        return RDAVersion.V2_2
    raise UnsupportedVersionError(
        f"unknown RDA magic prefix: {first_two_bytes[0:2]!r}"
    )


@dataclass(frozen=True)
class FileHeader:
    """RDA ファイルのヘッダ情報．"""

    magic: str
    version: RDAVersion
    unknown: bytes
    first_block_offset: int

    @property
    def header_size(self) -> int:
        """magic + unknown + firstBlockOffset の合計バイト数．"""
        return (
            len(magic_bytes(self.version))
            + _UNKNOWN_SIZES[self.version]
            + uint_size(self.version)
        )


def read_file_header(stream: BinaryIO) -> FileHeader:
    """ストリーム先頭から FileHeader を読み取る．

    呼び出し後，ストリーム位置は header 直後（データ領域先頭）になる．
    """
    head = stream.read(2)
    stream.seek(0)
    version = detect_version(head)

    expected_magic = _MAGIC_STRINGS[version]
    encoding = _MAGIC_ENCODINGS[version]
    magic_size = len(magic_bytes(version))

    raw_magic = stream.read(magic_size)
    if len(raw_magic) != magic_size:
        raise RDAParseError("file truncated in magic section")
    actual_magic = raw_magic.decode(encoding, errors="replace")
    if actual_magic != expected_magic:
        raise RDAParseError(
            f"magic mismatch: expected {expected_magic!r}, got {actual_magic!r}"
        )

    unknown = stream.read(_UNKNOWN_SIZES[version])
    if len(unknown) != _UNKNOWN_SIZES[version]:
        raise RDAParseError("file truncated in unknown section")

    first_block_offset = read_uint(stream, version)

    return FileHeader(
        magic=actual_magic,
        version=version,
        unknown=unknown,
        first_block_offset=first_block_offset,
    )
