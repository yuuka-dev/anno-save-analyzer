"""RDA parser の境界・異常系テスト．

test_rda.py に対し，defensive error path やライフサイクル branch を個別に検証して
coverage を 100% に押し上げることを目的とする．
合成フィクスチャを壊れた状態で食わせたり，archive_mod 内部 API を直接叩くなど，
正常運用では踏まない経路を意図的に発動させる．
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from anno_save_analyzer.parser.rda import (
    EncryptedBlockError,
    RDAArchive,
    RDAEntry,
    RDAParseError,
    RDAVersion,
)
from anno_save_analyzer.parser.rda import archive as archive_mod
from anno_save_analyzer.parser.rda import block as block_mod
from anno_save_analyzer.parser.rda import header as header_mod
from anno_save_analyzer.parser.rda.block import (
    FILENAME_SIZE,
    FLAG_COMPRESSED,
    FLAG_ENCRYPTED,
    FLAG_MEMORY_RESIDENT,
    BlockInfo,
    DirEntry,
    _parse_dir_entry,
    block_info_size,
    dir_entry_size,
    read_directory,
)
from anno_save_analyzer.parser.rda.header import (
    detect_version,
    magic_bytes,
    read_file_header,
    read_uint,
)

# =====================================================================
#  fixture builders
# =====================================================================


def _v22_header() -> bytes:
    return magic_bytes(RDAVersion.V2_2) + b"\x00" * 766


def _make_dir_entry(
    name: str,
    offset: int,
    compressed: int,
    uncompressed: int,
) -> bytes:
    fn = name.encode("utf-16-le").ljust(FILENAME_SIZE, b"\x00")
    return fn + struct.pack("<QQQQQ", offset, compressed, uncompressed, 1700000000, 0)


def _make_block_info(
    flags: int,
    file_count: int,
    directory_size: int,
    decompressed_size: int,
    next_block: int,
) -> bytes:
    return struct.pack(
        "<IIQQQ",
        flags,
        file_count,
        directory_size,
        decompressed_size,
        next_block,
    )


def _build_single_block_rda(
    entries: list[tuple[str, bytes]],
    *,
    flags: int = 0,
    override_directory_bytes: bytes | None = None,
    override_directory_size: int | None = None,
    override_decompressed_size: int | None = None,
    override_file_count: int | None = None,
    directory_pad_before: int = 0,
    extra_block_info: bytes | None = None,
) -> bytes:
    """単一ブロック RDA を柔軟なパラメータで合成する．"""
    version = RDAVersion.V2_2
    header = _v22_header()
    header_size = len(header) + 8  # + firstBlockOffset

    data_sections: list[bytes] = []
    dir_entries: list[bytes] = []
    cur = header_size
    for name, raw in entries:
        stored = zlib.compress(raw) if (flags & FLAG_COMPRESSED) else raw
        data_sections.append(stored)
        dir_entries.append(_make_dir_entry(name, cur, len(stored), len(raw)))
        cur += len(stored)

    dir_bytes = b"".join(dir_entries)
    decompressed_dir = len(dir_bytes)
    on_disk_dir = zlib.compress(dir_bytes) if (flags & FLAG_COMPRESSED) else dir_bytes
    if override_directory_bytes is not None:
        on_disk_dir = override_directory_bytes

    directory_size = (
        override_directory_size if override_directory_size is not None else len(on_disk_dir)
    )
    declared_decomp = (
        override_decompressed_size if override_decompressed_size is not None else decompressed_dir
    )
    declared_count = override_file_count if override_file_count is not None else len(entries)

    block_offset = (
        header_size + sum(len(d) for d in data_sections) + directory_pad_before + len(on_disk_dir)
    )
    file_size = block_offset + block_info_size(version)

    bi = _make_block_info(
        flags=flags,
        file_count=declared_count,
        directory_size=directory_size,
        decompressed_size=declared_decomp,
        next_block=file_size,
    )
    if extra_block_info is not None:
        bi = extra_block_info

    return (
        header
        + struct.pack("<Q", block_offset)
        + b"".join(data_sections)
        + b"\x00" * directory_pad_before
        + on_disk_dir
        + bi
    )


# =====================================================================
#  archive.py — lifecycle / open-close / property branches
# =====================================================================


class TestArchiveLifecycle:
    def test_open_is_idempotent(self, tmp_path: Path) -> None:
        """open() を 2 度呼んでも副作用を起こさない（早期 return path を踏む）．"""
        rda_path = tmp_path / "x.rda"
        rda_path.write_bytes(_build_single_block_rda([("a.txt", b"a")]))
        rda = RDAArchive(rda_path)
        rda.open()
        try:
            first_entries = rda.entries
            rda.open()  # 早期 return path
            assert rda.entries == first_entries
        finally:
            rda.close()

    def test_close_without_open_is_noop(self, tmp_path: Path) -> None:
        """open() していない RDAArchive に close() しても例外にならない（branch to exit）．"""
        rda = RDAArchive(tmp_path / "never-opened.rda")
        rda.close()  # 例外出なければ OK
        rda.close()  # 連続呼びも許容

    def test_accessing_header_before_open_raises(self, tmp_path: Path) -> None:
        rda = RDAArchive(tmp_path / "nothing.rda")
        with pytest.raises(RuntimeError, match="not open"):
            _ = rda.header

    def test_accessing_entries_after_close_raises(self, tmp_path: Path) -> None:
        rda_path = tmp_path / "x.rda"
        rda_path.write_bytes(_build_single_block_rda([("a.txt", b"a")]))
        rda = RDAArchive(rda_path)
        with rda:
            pass  # open, then close via context manager
        with pytest.raises(RuntimeError, match="not open"):
            _ = rda.entries


# =====================================================================
#  archive.py — extract / read error paths
# =====================================================================


class TestArchiveIO:
    def test_extract_to_explicit_file_path(self, tmp_path: Path) -> None:
        """dest が既存 dir でない場合はそのパスにファイル作成（単一 extract の非 dir 分岐）．"""
        rda_path = tmp_path / "x.rda"
        rda_path.write_bytes(_build_single_block_rda([("a.txt", b"alpha")]))
        dest_file = tmp_path / "output" / "renamed.txt"
        with RDAArchive(rda_path) as rda:
            out = rda.extract("a.txt", dest_file)
        assert out == dest_file
        assert dest_file.read_bytes() == b"alpha"

    def test_extract_into_existing_directory(self, tmp_path: Path) -> None:
        rda_path = tmp_path / "x.rda"
        rda_path.write_bytes(_build_single_block_rda([("named.txt", b"bravo")]))
        dest_dir = tmp_path / "outdir"
        dest_dir.mkdir()
        with RDAArchive(rda_path) as rda:
            out = rda.extract("named.txt", dest_dir)
        assert out == dest_dir / "named.txt"
        assert out.read_bytes() == b"bravo"

    def test_extract_all_writes_every_entry(self, tmp_path: Path) -> None:
        """複数エントリを extract_all で一括展開．CI (sample.a7s 無し) でも通る合成ケース．"""
        rda_path = tmp_path / "multi.rda"
        rda_path.write_bytes(
            _build_single_block_rda(
                [
                    ("alpha.bin", b"AAA"),
                    ("beta.bin", b"BBBB"),
                    ("gamma.bin", b"CCCCC"),
                ]
            )
        )
        dest_root = tmp_path / "out_all"
        with RDAArchive(rda_path) as rda:
            paths = rda.extract_all(dest_root)
        assert {p.name for p in paths} == {"alpha.bin", "beta.bin", "gamma.bin"}
        assert (dest_root / "alpha.bin").read_bytes() == b"AAA"
        assert (dest_root / "beta.bin").read_bytes() == b"BBBB"
        assert (dest_root / "gamma.bin").read_bytes() == b"CCCCC"

    def test_extract_all_creates_subdirectories_from_embedded_paths(
        self, tmp_path: Path
    ) -> None:
        """エントリ名にスラッシュが含まれる場合にサブディレクトリを作ることを確認．"""
        rda_path = tmp_path / "nested.rda"
        # ``\`` を含む名前も含め，正規化 (lstrip("/") / ``\\`` → ``/``) 経路を踏む
        rda_path.write_bytes(
            _build_single_block_rda(
                [
                    ("/leading-slash.bin", b"L"),
                    ("gfx\\sub\\foo.bin", b"F"),
                ]
            )
        )
        dest_root = tmp_path / "nested_out"
        with RDAArchive(rda_path) as rda:
            paths = rda.extract_all(dest_root)
        # 正規化後のパスを確認
        rels = sorted(str(p.relative_to(dest_root)) for p in paths)
        assert rels == sorted(["leading-slash.bin", "gfx/sub/foo.bin"])
        assert (dest_root / "gfx" / "sub" / "foo.bin").read_bytes() == b"F"
        assert (dest_root / "leading-slash.bin").read_bytes() == b"L"

    def test_read_encrypted_entry_rejected(self, tmp_path: Path) -> None:
        """
        直接 RDAEntry を encrypted flag 付きで構築して ``_read_entry_data`` を叩く．
        実ファイル上の Encrypted ブロックは directory 読取側 (block.read_directory) で
        先に弾かれるため，file 側の guard は別ルートで発火させる必要がある．
        """
        rda_path = tmp_path / "ok.rda"
        rda_path.write_bytes(_build_single_block_rda([("a.txt", b"a")]))
        with RDAArchive(rda_path) as rda:
            fake = RDAEntry(
                filename="a.txt",
                offset=100,
                compressed_size=10,
                uncompressed_size=10,
                timestamp=0,
                flags=FLAG_ENCRYPTED,
                _version=RDAVersion.V2_2,
            )
            with pytest.raises(EncryptedBlockError):
                rda._read_entry_data(fake)

    def test_read_truncated_entry_raises(self, tmp_path: Path) -> None:
        """offset + compressed_size が EOF を越えるエントリは RDAParseError を投げる．"""
        rda_path = tmp_path / "ok.rda"
        rda_path.write_bytes(_build_single_block_rda([("a.txt", b"a")]))
        file_size = rda_path.stat().st_size
        with RDAArchive(rda_path) as rda:
            fake = RDAEntry(
                filename="phantom",
                offset=file_size - 4,
                compressed_size=1024,
                uncompressed_size=1024,
                timestamp=0,
                flags=0,
                _version=RDAVersion.V2_2,
            )
            with pytest.raises(RDAParseError, match="unexpected EOF"):
                rda._read_entry_data(fake)

    def test_read_broken_zlib_entry_raises(self, tmp_path: Path) -> None:
        """Compressed flag 付きなのに中身が zlib 不正ならエラー．"""
        rda_path = tmp_path / "ok.rda"
        # 8 バイト以上の有効な offset を確保するため追加データ埋めた RDA を作る．
        rda_path.write_bytes(_build_single_block_rda([("a.txt", b"A" * 64)]))
        with RDAArchive(rda_path) as rda:
            first = rda.entries[0]
            # 実データは plain だが，flags だけ Compressed を強制付与
            fake = RDAEntry(
                filename=first.filename,
                offset=first.offset,
                compressed_size=first.compressed_size,
                uncompressed_size=first.uncompressed_size,
                timestamp=first.timestamp,
                flags=FLAG_COMPRESSED,
                _version=RDAVersion.V2_2,
            )
            with pytest.raises(RDAParseError, match="zlib decompress"):
                rda._read_entry_data(fake)


# =====================================================================
#  archive.py — block chain loop guard
# =====================================================================


class TestBlockChainLoopGuard:
    def test_self_referential_block_chain_triggers_guard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """nextBlock が自身を指す RDA は loop guard で検出され RDAParseError になる．

        guard 定数を 3 に下げてループ検出を高速に発動．
        """
        monkeypatch.setattr(archive_mod, "MAX_BLOCK_CHAIN_LENGTH", 3)

        header = _v22_header()
        header_size = len(header) + 8
        # 1 件 file, 1 directory の block を作り，nextBlock を block 自身の offset にする
        entry_bytes = _make_dir_entry("a.txt", header_size, 1, 1)
        directory = entry_bytes  # 1 entry, 非圧縮
        block_offset = header_size + 1 + len(directory)  # file 1B + directory
        bi = _make_block_info(
            flags=0,
            file_count=1,
            directory_size=len(directory),
            decompressed_size=len(directory),
            next_block=block_offset,  # 自己参照
        )
        rda = header + struct.pack("<Q", block_offset) + b"X" + directory + bi
        rda_path = tmp_path / "loop.rda"
        rda_path.write_bytes(rda)

        with pytest.raises(RDAParseError, match="loop detected"), RDAArchive(rda_path):
            pass


# =====================================================================
#  archive.py — _entry_from MemoryResident branch
# =====================================================================


class TestEntryFromBranches:
    def test_entry_from_drops_flags_for_memory_resident_block(self) -> None:
        """MemoryResident ブロックの entry は Compressed/Encrypted flag を引き継がない．"""
        mr_block = BlockInfo(
            flags=FLAG_MEMORY_RESIDENT | FLAG_COMPRESSED,
            file_count=1,
            directory_size=0,
            decompressed_size=0,
            next_block=0,
        )
        de = DirEntry(
            filename="x.bin",
            offset=0,
            compressed_size=1,
            uncompressed_size=1,
            timestamp=0,
            unknown=0,
        )
        entry = archive_mod._entry_from(de, mr_block, RDAVersion.V2_2)
        assert entry.flags == 0  # Compressed が伝播していない
        assert not entry.is_compressed

    def test_entry_from_propagates_compressed_for_plain_block(self) -> None:
        plain = BlockInfo(
            flags=FLAG_COMPRESSED,
            file_count=1,
            directory_size=0,
            decompressed_size=0,
            next_block=0,
        )
        de = DirEntry(
            filename="x.bin",
            offset=0,
            compressed_size=1,
            uncompressed_size=1,
            timestamp=0,
            unknown=0,
        )
        entry = archive_mod._entry_from(de, plain, RDAVersion.V2_2)
        assert entry.is_compressed


# =====================================================================
#  block.py — read_block_info / read_directory error paths
# =====================================================================


class TestBlockErrors:
    def test_block_info_eof_raises(self, tmp_path: Path) -> None:
        """firstBlockOffset の直後に残り 4B しか置かず BlockInfo 読取で EOF を起こす．"""
        header = _v22_header()
        # firstBlockOffset を header 直後 (= header + 8B 自身の後) に設定 → 残り 4B しかない
        first_block_offset = len(header) + 8
        rda = header + struct.pack("<Q", first_block_offset) + b"\x00\x01\x02\x03"
        rda_path = tmp_path / "truncated.rda"
        rda_path.write_bytes(rda)
        with pytest.raises(RDAParseError), RDAArchive(rda_path):
            pass

    def test_parse_dir_entry_buffer_too_small(self) -> None:
        with pytest.raises(RDAParseError, match="too small"):
            _parse_dir_entry(b"\x00" * 10, RDAVersion.V2_2)

    def test_directory_start_underflow(self, tmp_path: Path) -> None:
        """block_offset より大きい directory_size を宣言 → dir_start 負数で RDAParseError．"""
        version = RDAVersion.V2_2
        header = _v22_header()
        header_size = len(header) + 8
        block_offset = header_size  # header 直後に block 配置（前に directory 分のスペース無し）
        bi = _make_block_info(
            flags=0,
            file_count=0,
            directory_size=header_size + 1000,  # わざと大きく
            decompressed_size=header_size + 1000,
            next_block=block_offset + block_info_size(version),
        )
        rda = header + struct.pack("<Q", block_offset) + bi
        rda_path = tmp_path / "underflow.rda"
        rda_path.write_bytes(rda)
        with pytest.raises(RDAParseError, match="underflow"), RDAArchive(rda_path):
            pass

    def test_directory_eof_raises_via_truncated_stream(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """directory バイト列を正規に読み取ろうとしたら短く返ってきた場合の guard．

        実 RDA では先行の underflow チェックや ``block_offset < file_size`` 不変条件で
        この guard には到達しない．ストリームの ``read`` を patch して短いレスポンスを
        強制することで defensive check の発火を検証する．
        """
        rda_path = tmp_path / "ok.rda"
        rda_path.write_bytes(_build_single_block_rda([("a.txt", b"a")]))

        real_read = None

        def short_read(self_stream, size: int = -1) -> bytes:  # type: ignore[no-untyped-def]
            data = real_read(size)
            # directory バイトを読むサイズ (560 = V2.2 DirEntry) のとき切り詰める
            if size == dir_entry_size(RDAVersion.V2_2):
                return data[:-1]
            return data

        # ファイルを手動で開いて短縮 read を仕込む．RDAArchive 同様に自前ライフタイム管理
        stream = open(rda_path, "rb")  # noqa: SIM115
        real_read = stream.read
        monkeypatch.setattr(stream, "read", lambda size=-1: short_read(stream, size))
        try:
            version = RDAVersion.V2_2
            stream.seek(len(_v22_header()) + 8)  # skip header
            # 本物の block_info 読取位置を特定するためアーカイブ経由で offset を取る
            with RDAArchive(rda_path) as arc:
                block_offset = arc.header.first_block_offset
            # 新しく patched stream で directory 読取のみ実行
            stream.seek(block_offset)
            from anno_save_analyzer.parser.rda.block import read_block_info

            bi = read_block_info(stream, version)
            with pytest.raises(RDAParseError, match="unexpected EOF while reading directory"):
                read_directory(stream, block_offset, bi, version)
        finally:
            stream.close()

    def test_directory_zlib_invalid_raises(self, tmp_path: Path) -> None:
        """Compressed flag 立ってるのに directory バイト列が zlib 不正．"""
        garbage = b"\xde\xad\xbe\xef" * 8
        rda = _build_single_block_rda(
            [("a.txt", b"x")],
            flags=FLAG_COMPRESSED,
            override_directory_bytes=garbage,
            override_directory_size=len(garbage),
            override_decompressed_size=dir_entry_size(RDAVersion.V2_2),
        )
        rda_path = tmp_path / "badzlib.rda"
        rda_path.write_bytes(rda)
        with pytest.raises(RDAParseError, match="zlib decompress"), RDAArchive(rda_path):
            pass

    def test_directory_decompressed_size_mismatch(self, tmp_path: Path) -> None:
        """Compressed 正常 → しかし BlockInfo.decompressed_size が嘘ならエラー．"""
        version = RDAVersion.V2_2
        header = _v22_header()
        header_size = len(header) + 8

        # 正当な 1 件 directory を zlib 圧縮
        entry_bytes = _make_dir_entry("a.txt", header_size, 1, 1)
        dir_bytes = entry_bytes  # 実サイズ
        compressed_dir = zlib.compress(dir_bytes)

        block_offset = header_size + 1 + len(compressed_dir)
        bi = _make_block_info(
            flags=FLAG_COMPRESSED,
            file_count=1,
            directory_size=len(compressed_dir),
            decompressed_size=len(dir_bytes) + 1000,  # 嘘
            next_block=block_offset + block_info_size(version),
        )
        rda = header + struct.pack("<Q", block_offset) + b"X" + compressed_dir + bi
        rda_path = tmp_path / "dirsize.rda"
        rda_path.write_bytes(rda)
        with (
            pytest.raises(RDAParseError, match="decompressed directory size"),
            RDAArchive(rda_path),
        ):
            pass

    def test_directory_file_count_mismatch(self, tmp_path: Path) -> None:
        """file_count * entry_size != decompressed_size で整合性エラー．"""
        rda = _build_single_block_rda(
            [("a.txt", b"x")],
            override_file_count=5,  # 実際は 1 件しかないのに 5 と言い張る
        )
        rda_path = tmp_path / "count.rda"
        rda_path.write_bytes(rda)
        with (
            pytest.raises(RDAParseError, match="size/fileCount mismatch"),
            RDAArchive(rda_path),
        ):
            pass


# =====================================================================
#  block.py — MemoryResident directory offset adjustment
# =====================================================================


class TestMemoryResidentDirectory:
    def test_memory_resident_directory_offset_shifts_by_2_uints(self, tmp_path: Path) -> None:
        """MR flag 付きブロックは directory を ``block_offset - dir_size - 2*uint`` から読む．

        本実装は MR の packed data 解凍まではしないが，directory 読取と entry 列挙までは通る．
        """
        version = RDAVersion.V2_2
        header = _v22_header()
        header_size = len(header) + 8

        entry_bytes = _make_dir_entry("packed.bin", 0, 1, 1)  # offset=0 は相対値
        dir_bytes = entry_bytes
        decompressed = len(dir_bytes)

        # MR layout:
        # [packed placeholder (1B)] [directory] [MR header (2 uints)] [BlockInfo]
        # directory 開始位置 = block_offset - dir_size - 2*uint
        mr_header = struct.pack("<QQ", 1, 1)
        packed_placeholder = b"\xff"
        block_offset = header_size + len(packed_placeholder) + len(dir_bytes) + len(mr_header)
        bi = _make_block_info(
            flags=FLAG_MEMORY_RESIDENT,
            file_count=1,
            directory_size=len(dir_bytes),
            decompressed_size=decompressed,
            next_block=block_offset + block_info_size(version),
        )
        rda = (
            header
            + struct.pack("<Q", block_offset)
            + packed_placeholder
            + dir_bytes
            + mr_header
            + bi
        )
        rda_path = tmp_path / "mr.rda"
        rda_path.write_bytes(rda)

        with RDAArchive(rda_path) as rda:
            assert rda.entry_names() == ["packed.bin"]
            # MR entry は個別 Compressed flag を持たない
            assert rda.entries[0].flags == 0


# =====================================================================
#  header.py — EOF / version detection / magic mismatch
# =====================================================================


class TestHeaderErrors:
    def test_read_uint_eof(self) -> None:
        import io

        with pytest.raises(RDAParseError, match="unexpected EOF while reading uint"):
            read_uint(io.BytesIO(b"\x00\x01"), RDAVersion.V2_2)  # 2B しかない，8B 期待

    def test_detect_version_requires_two_bytes(self) -> None:
        with pytest.raises(RDAParseError, match="too small"):
            detect_version(b"R")

    def test_truncated_magic_raises(self, tmp_path: Path) -> None:
        """magic の途中で切れている（先頭 ``Re`` で V2.2 判定 → 続きが足りない）．"""
        import io

        # 先頭 2B で V2.2 判定されるが実際の magic は 18B 必要．3B で切れてる
        stream = io.BytesIO(b"Res")
        with pytest.raises(RDAParseError, match="truncated in magic"):
            read_file_header(stream)

    def test_magic_mismatch_raises(self, tmp_path: Path) -> None:
        """先頭 2B が ``Re`` だが残り 16B がデタラメで mismatch．"""
        import io

        bogus = b"Re" + b"X" * 16  # magic 長 18B を埋めるがマッチしない
        stream = io.BytesIO(bogus + b"\x00" * 800)
        with pytest.raises(RDAParseError, match="magic mismatch"):
            read_file_header(stream)

    def test_unknown_section_truncated(self, tmp_path: Path) -> None:
        """magic は正規だが unknown 領域 (766B) の途中で切れている．"""
        import io

        magic = magic_bytes(RDAVersion.V2_2)
        stream = io.BytesIO(magic + b"\x00" * 100)  # unknown 100B しかない
        with pytest.raises(RDAParseError, match="truncated in unknown"):
            read_file_header(stream)


# =====================================================================
#  sanity
# =====================================================================


def test_header_size_property_reports_v22_total() -> None:
    h = read_file_header(__import__("io").BytesIO(_v22_header() + struct.pack("<Q", 0)))
    assert h.header_size == 18 + 766 + 8  # V2.2 仕様上の合計


def test_detect_version_v20_prefix() -> None:
    # UTF-16LE 前提の R\x00 で V2.0 判定が走るブランチを踏む
    assert detect_version(b"R\x00") is RDAVersion.V2_0


def _silence_unused_imports() -> None:
    # coverage 対象外の静的参照で import 未使用警告を防ぐ
    _ = (block_mod, header_mod)
