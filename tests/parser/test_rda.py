"""RDA パーサの pytest．

sample.a7s はリポジトリ直下にある書記長の実セーブ．
CI など存在しない環境では ``SAMPLE_A7S`` 環境変数で override でき，
見つからない場合は実セーブ必須テストを自動 skip する．

単体テスト（構造検証・エラーハンドリング）は sample に依存せず，
合成フィクスチャをその場で作って走らせる．
"""

from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path

import pytest

from anno_save_analyzer.parser.rda import (
    EncryptedBlockError,
    RDAArchive,
    RDAParseError,
    RDAVersion,
    UnsupportedVersionError,
)
from anno_save_analyzer.parser.rda.block import (
    FILENAME_SIZE,
    FLAG_COMPRESSED,
    FLAG_DELETED,
    FLAG_ENCRYPTED,
    block_info_size,
    dir_entry_size,
)
from anno_save_analyzer.parser.rda.header import (
    magic_bytes,
)

# --------- 実セーブ依存テスト ---------

_DEFAULT_SAMPLE = Path(__file__).resolve().parents[2] / "sample.a7s"
SAMPLE_PATH = Path(os.environ.get("SAMPLE_A7S", _DEFAULT_SAMPLE))
_HAS_SAMPLE = SAMPLE_PATH.is_file()


@pytest.mark.skipif(not _HAS_SAMPLE, reason=f"sample save not found: {SAMPLE_PATH}")
class TestRealSample:
    def test_version_is_v2_2(self) -> None:
        with RDAArchive(SAMPLE_PATH) as rda:
            assert rda.version is RDAVersion.V2_2
            assert rda.header.magic == "Resource File V2.2"

    def test_enumerates_four_entries(self) -> None:
        with RDAArchive(SAMPLE_PATH) as rda:
            names = {e.filename for e in rda.entries}
            assert names == {"meta.a7s", "header.a7s", "gamesetup.a7s", "data.a7s"}

    def test_entry_sizes_positive_and_monotonic(self) -> None:
        with RDAArchive(SAMPLE_PATH) as rda:
            for e in rda.entries:
                assert e.compressed_size > 0
                assert e.uncompressed_size >= e.compressed_size  # 非圧縮時は等しい

    def test_read_data_a7s_then_zlib_roundtrip(self) -> None:
        """CLAUDE.md の成功条件スクリプトそのもの．"""
        with RDAArchive(SAMPLE_PATH) as rda:
            data_bytes = rda.read("data.a7s")
            inner = zlib.decompress(data_bytes)
            assert len(inner) > 1000

    def test_extract_all(self, tmp_path: Path) -> None:
        with RDAArchive(SAMPLE_PATH) as rda:
            paths = rda.extract_all(tmp_path)
            assert {p.name for p in paths} == {
                "meta.a7s",
                "header.a7s",
                "gamesetup.a7s",
                "data.a7s",
            }
            for p in paths:
                assert p.stat().st_size > 0

    def test_missing_entry_raises_key_error(self) -> None:
        with RDAArchive(SAMPLE_PATH) as rda, pytest.raises(KeyError):
            rda.read("does_not_exist.a7s")


# --------- 合成フィクスチャによる単体テスト ---------


def _build_minimal_rda(
    files: list[tuple[str, bytes]],
    *,
    compressed: bool = False,
) -> bytes:
    """V2.2 RDA の最小アーカイブバイト列を合成する．

    1 ブロック / fileCount=len(files) / 暗号化なし．
    ``compressed=True`` で block flags に FLAG_COMPRESSED を立て，
    directory と各ファイルを同時に zlib 圧縮する（実 RDA と同じ取り扱い）．
    """
    version = RDAVersion.V2_2
    magic = magic_bytes(version)
    unknown = b"\x00" * 766

    # 1. まず payload (データ + directory + BlockInfo) を組み立てる
    header_size = len(magic) + len(unknown) + 8  # +8: firstBlockOffset (u64)

    data_sections: list[bytes] = []
    dir_entries: list[bytes] = []
    current_offset = header_size

    flags = FLAG_COMPRESSED if compressed else 0

    for name, payload in files:
        stored = zlib.compress(payload) if compressed else payload
        # DirEntry: filename(520) + offset + compressed + filesize + timestamp + unknown (all u64)
        fn_bytes = name.encode("utf-16-le").ljust(FILENAME_SIZE, b"\x00")
        assert len(fn_bytes) == FILENAME_SIZE
        entry = fn_bytes + struct.pack(
            "<QQQQQ",
            current_offset,
            len(stored),
            len(payload),
            1700000000,  # timestamp
            0,
        )
        assert len(entry) == dir_entry_size(version)
        dir_entries.append(entry)
        data_sections.append(stored)
        current_offset += len(stored)

    directory_bytes = b"".join(dir_entries)
    decompressed_size = len(directory_bytes)
    directory_on_disk = zlib.compress(directory_bytes) if compressed else directory_bytes

    # directory 配置後に BlockInfo．block_offset = header + data + directory
    block_offset = header_size + sum(len(d) for d in data_sections) + len(directory_on_disk)
    file_size = block_offset + block_info_size(version)

    block_info = struct.pack(
        "<IIQQQ",
        flags,
        len(files),
        len(directory_on_disk),  # directorySize
        decompressed_size,  # decompressedSize (directory 展開後)
        file_size,  # nextBlock = EOF でチェーン終端
    )
    assert len(block_info) == block_info_size(version)

    return (
        magic
        + unknown
        + struct.pack("<Q", block_offset)
        + b"".join(data_sections)
        + directory_on_disk
        + block_info
    )


class TestSyntheticFixture:
    def test_round_trip_uncompressed(self, tmp_path: Path) -> None:
        rda_path = tmp_path / "tiny.rda"
        rda_path.write_bytes(
            _build_minimal_rda(
                [("hello.txt", b"hi"), ("big.bin", b"A" * 4096)],
                compressed=False,
            )
        )
        with RDAArchive(rda_path) as rda:
            assert rda.version is RDAVersion.V2_2
            assert rda.entry_names() == ["hello.txt", "big.bin"]
            assert rda.read("hello.txt") == b"hi"
            assert rda.read("big.bin") == b"A" * 4096

    def test_round_trip_compressed(self, tmp_path: Path) -> None:
        """FLAG_COMPRESSED は directory と各ファイル両方に同時適用される．"""
        payload = b"xyz" * 2048
        rda_path = tmp_path / "comp.rda"
        rda_path.write_bytes(
            _build_minimal_rda(
                [("a.txt", b"alpha"), ("payload.bin", payload)],
                compressed=True,
            )
        )
        with RDAArchive(rda_path) as rda:
            assert rda.entry_names() == ["a.txt", "payload.bin"]
            entry = rda.get_entry("payload.bin")
            assert entry.is_compressed
            assert entry.compressed_size < entry.uncompressed_size
            assert rda.read("a.txt") == b"alpha"
            assert rda.read("payload.bin") == payload


# --------- エラーハンドリング ---------


class TestErrorHandling:
    def test_bad_magic_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.rda"
        bad.write_bytes(b"\x00\x01not an RDA at all")
        with pytest.raises(UnsupportedVersionError), RDAArchive(bad):
            pass

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "empty.rda"
        bad.write_bytes(b"")
        with pytest.raises(RDAParseError), RDAArchive(bad):
            pass

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError), RDAArchive(tmp_path / "nothing.rda"):
            pass

    def test_unknown_entry_raises(self, tmp_path: Path) -> None:
        rda_path = tmp_path / "x.rda"
        rda_path.write_bytes(_build_minimal_rda([("only.txt", b"x")], compressed=False))
        with RDAArchive(rda_path) as rda, pytest.raises(KeyError):
            rda.get_entry("missing.txt")

    def test_encrypted_block_rejected(self, tmp_path: Path) -> None:
        """Encrypted flag を立てたブロックは明示的に例外を送出する．"""
        rda_path = tmp_path / "enc.rda"
        raw = bytearray(_build_minimal_rda([("a.txt", b"hi")], compressed=False))
        # 末尾 BlockInfo の flags フィールドに FLAG_ENCRYPTED を立てる
        bi_size = block_info_size(RDAVersion.V2_2)
        block_start = len(raw) - bi_size
        (flags_old,) = struct.unpack("<I", raw[block_start : block_start + 4])
        flags_new = flags_old | FLAG_ENCRYPTED
        raw[block_start : block_start + 4] = struct.pack("<I", flags_new)
        rda_path.write_bytes(bytes(raw))

        with pytest.raises(EncryptedBlockError), RDAArchive(rda_path):
            pass

    def test_deleted_block_is_skipped(self, tmp_path: Path) -> None:
        """Deleted flag を立てたブロックはエントリ列挙から除外される．"""
        rda_path = tmp_path / "del.rda"
        raw = bytearray(_build_minimal_rda([("a.txt", b"hi")], compressed=False))
        bi_size = block_info_size(RDAVersion.V2_2)
        block_start = len(raw) - bi_size
        (flags_old,) = struct.unpack("<I", raw[block_start : block_start + 4])
        flags_new = flags_old | FLAG_DELETED
        raw[block_start : block_start + 4] = struct.pack("<I", flags_new)
        rda_path.write_bytes(bytes(raw))

        with RDAArchive(rda_path) as rda:
            assert rda.entries == []
