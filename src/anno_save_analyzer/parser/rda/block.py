"""BlockInfo / DirEntry 構造体および block chain 走査．

BlockInfo は自身の offset の直前に directory を置く点に注意．
directory は flag によって zlib 圧縮や XOR 暗号化されている．
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import BinaryIO

from .exceptions import EncryptedBlockError, RDAParseError
from .header import RDAVersion, read_uint, uint_size

# ---- flag ビット ----
FLAG_COMPRESSED = 0x01
FLAG_ENCRYPTED = 0x02
FLAG_MEMORY_RESIDENT = 0x04
FLAG_DELETED = 0x08

# ---- DirEntry レイアウト ----
FILENAME_SIZE = 520  # UTF-16LE, null padded


def block_info_size(version: RDAVersion) -> int:
    """BlockInfo の総バイト数．V2.0=20, V2.2=32．"""
    # flags(4) + fileCount(4) + uint*3
    return 4 + 4 + uint_size(version) * 3


def dir_entry_size(version: RDAVersion) -> int:
    """DirEntry の総バイト数．V2.0=540, V2.2=560．"""
    # filename(520) + uint*5
    return FILENAME_SIZE + uint_size(version) * 5


@dataclass(frozen=True)
class BlockInfo:
    """ブロックチェーンの 1 ノード．directory 位置は block_offset から逆算する．"""

    flags: int
    file_count: int
    directory_size: int
    decompressed_size: int
    next_block: int

    @property
    def is_compressed(self) -> bool:
        return bool(self.flags & FLAG_COMPRESSED)

    @property
    def is_encrypted(self) -> bool:
        return bool(self.flags & FLAG_ENCRYPTED)

    @property
    def is_memory_resident(self) -> bool:
        return bool(self.flags & FLAG_MEMORY_RESIDENT)

    @property
    def is_deleted(self) -> bool:
        return bool(self.flags & FLAG_DELETED)


def read_block_info(stream: BinaryIO, version: RDAVersion) -> BlockInfo:
    """ストリームの現在位置から BlockInfo を 1 件読み取る．"""
    raw = stream.read(8)
    if len(raw) != 8:
        raise RDAParseError("unexpected EOF while reading BlockInfo flags/fileCount")
    flags, file_count = struct.unpack("<II", raw)
    directory_size = read_uint(stream, version)
    decompressed_size = read_uint(stream, version)
    next_block = read_uint(stream, version)
    return BlockInfo(
        flags=flags,
        file_count=file_count,
        directory_size=directory_size,
        decompressed_size=decompressed_size,
        next_block=next_block,
    )


@dataclass(frozen=True)
class DirEntry:
    """ブロックの directory 内 1 エントリ．ファイル本体の位置とサイズを指す．"""

    filename: str
    offset: int
    compressed_size: int
    uncompressed_size: int
    timestamp: int
    unknown: int


def _parse_dir_entry(buf: bytes, version: RDAVersion) -> DirEntry:
    """decode 済みディレクトリバッファから 1 件分の DirEntry を組み立てる．"""
    if len(buf) < dir_entry_size(version):
        raise RDAParseError("DirEntry buffer too small")

    filename_bytes = buf[:FILENAME_SIZE]
    filename = filename_bytes.decode("utf-16-le", errors="replace").rstrip("\x00")

    pos = FILENAME_SIZE
    u = uint_size(version)
    fmt = "<I" if u == 4 else "<Q"

    def next_uint() -> int:
        nonlocal pos
        val = struct.unpack(fmt, buf[pos : pos + u])[0]
        pos += u
        return val

    offset = next_uint()
    compressed = next_uint()
    filesize = next_uint()
    timestamp = next_uint()
    unknown = next_uint()

    return DirEntry(
        filename=filename,
        offset=offset,
        compressed_size=compressed,
        uncompressed_size=filesize,
        timestamp=timestamp,
        unknown=unknown,
    )


def read_directory(
    stream: BinaryIO,
    block_offset: int,
    block: BlockInfo,
    version: RDAVersion,
) -> list[DirEntry]:
    """block の直前領域から directory を読み出し，DirEntry のリストを返す．

    Encrypted ブロックは v0.1.0 では未対応で例外を送出する．
    MemoryResident ブロックは本関数では追加ヘッダ処理を行わず，directory 本体のみを読む．
    """
    if block.is_encrypted:
        raise EncryptedBlockError(
            "encrypted directory block is not supported in v0.1.0"
        )

    dir_start = block_offset - block.directory_size
    if block.is_memory_resident:
        # MemoryResident はさらに 2 * uintSize 分前に compressed/uncompressed header
        dir_start -= 2 * uint_size(version)

    if dir_start < 0:
        raise RDAParseError(
            f"directory start offset underflow (block={block_offset}, dir_size={block.directory_size})"
        )

    stream.seek(dir_start)
    raw = stream.read(block.directory_size)
    if len(raw) != block.directory_size:
        raise RDAParseError("unexpected EOF while reading directory bytes")

    if block.is_compressed:
        try:
            raw = zlib.decompress(raw)
        except zlib.error as e:
            raise RDAParseError(f"zlib decompress failed for directory: {e}") from e

    entry_sz = dir_entry_size(version)
    expected = block.file_count * entry_sz
    if block.is_compressed:
        if len(raw) != block.decompressed_size:
            raise RDAParseError(
                f"decompressed directory size mismatch "
                f"(got {len(raw)}, want {block.decompressed_size})"
            )
    # 非圧縮時は directory_size == decompressed_size である前提．
    if expected != block.decompressed_size:
        raise RDAParseError(
            f"directory size/fileCount mismatch "
            f"(fileCount*entry_sz={expected}, decompressed_size={block.decompressed_size})"
        )

    entries: list[DirEntry] = []
    for i in range(block.file_count):
        start = i * entry_sz
        entries.append(_parse_dir_entry(raw[start : start + entry_sz], version))
    return entries
