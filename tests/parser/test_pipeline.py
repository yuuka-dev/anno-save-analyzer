"""parser.pipeline の pytest．

合成フィクスチャ（中に zlib 二重圧縮された data.a7s を埋めた擬似 RDA）を作り，
extract_inner_filedb が想定通りに 2 段階解凍して FileDB 相当のバイトを返すことを確認する．
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from anno_save_analyzer.parser.pipeline import extract_inner_filedb
from anno_save_analyzer.parser.rda.block import (
    FILENAME_SIZE,
    block_info_size,
    dir_entry_size,
)
from anno_save_analyzer.parser.rda.header import RDAVersion, magic_bytes


def _build_rda_wrapping_zlib_payload(inner_bytes: bytes) -> bytes:
    """``data.a7s`` エントリ 1 件だけ持ち，その中身が zlib 圧縮された inner_bytes である最小 RDA を作る．"""
    version = RDAVersion.V2_2
    magic = magic_bytes(version)
    unknown = b"\x00" * 766
    header_size = len(magic) + len(unknown) + 8

    zipped = zlib.compress(inner_bytes)

    # 1 件だけの DirEntry
    fn_bytes = "data.a7s".encode("utf-16-le").ljust(FILENAME_SIZE, b"\x00")
    dir_entry = fn_bytes + struct.pack(
        "<QQQQQ",
        header_size,  # offset: ヘッダ直後に file データ本体
        len(zipped),  # compressed size (non-block-compressed: stored as-is)
        len(zipped),  # uncompressed size (block 非圧縮なので等価)
        1700000000,
        0,
    )
    assert len(dir_entry) == dir_entry_size(version)

    block_offset = header_size + len(zipped) + len(dir_entry)
    file_size = block_offset + block_info_size(version)

    block_info = struct.pack(
        "<IIQQQ",
        0,  # flags: 全部 off
        1,  # fileCount
        len(dir_entry),
        len(dir_entry),
        file_size,  # nextBlock = EOF
    )

    return magic + unknown + struct.pack("<Q", block_offset) + zipped + dir_entry + block_info


def test_extract_inner_filedb_returns_decompressed_bytes(tmp_path: Path) -> None:
    payload = b"FileDB-ish payload " * 1024
    rda_path = tmp_path / "fake.a7s"
    rda_path.write_bytes(_build_rda_wrapping_zlib_payload(payload))

    result = extract_inner_filedb(rda_path)
    assert result == payload


def test_extract_inner_filedb_writes_dest_file(tmp_path: Path) -> None:
    payload = b"payload for dest" * 256
    rda_path = tmp_path / "fake.a7s"
    rda_path.write_bytes(_build_rda_wrapping_zlib_payload(payload))

    dest = tmp_path / "inner.bin"
    result = extract_inner_filedb(rda_path, dest=dest)
    assert result == payload
    assert dest.read_bytes() == payload
