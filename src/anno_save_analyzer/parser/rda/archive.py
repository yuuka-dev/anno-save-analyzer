"""RDAArchive: RDA ファイルの公開 API．

context manager で開き，エントリ列挙と個別ファイル取り出しを提供する．
"""

from __future__ import annotations

import os
import zlib
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Iterator

from .block import (
    BlockInfo,
    DirEntry,
    FLAG_COMPRESSED,
    FLAG_ENCRYPTED,
    read_block_info,
    read_directory,
)
from .exceptions import EncryptedBlockError, RDAParseError
from .header import FileHeader, RDAVersion, read_file_header


@dataclass(frozen=True)
class RDAEntry:
    """ユーザが触る公開版のファイルエントリ．"""

    filename: str
    offset: int
    compressed_size: int
    uncompressed_size: int
    timestamp: int
    flags: int
    _version: RDAVersion

    @property
    def is_compressed(self) -> bool:
        return bool(self.flags & FLAG_COMPRESSED)

    @property
    def is_encrypted(self) -> bool:
        return bool(self.flags & FLAG_ENCRYPTED)


def _entry_from(
    dir_entry: DirEntry, block: BlockInfo, version: RDAVersion
) -> RDAEntry:
    # RDAFile.FromUnmanaged と同じロジック: block flag を file flag として引き継ぐ．
    # ただし MemoryResident (4) / Deleted (8) の場合は Compressed/Encrypted を個別 file 属性としない．
    flags = 0
    if not (block.flags & 0x04):  # not MemoryResident
        flags = block.flags & (FLAG_COMPRESSED | FLAG_ENCRYPTED)
    # MemoryResident は本実装では data 取り出しで別扱いするが，現状未サポート．
    return RDAEntry(
        filename=dir_entry.filename,
        offset=dir_entry.offset,
        compressed_size=dir_entry.compressed_size,
        uncompressed_size=dir_entry.uncompressed_size,
        timestamp=dir_entry.timestamp,
        flags=flags,
        _version=version,
    )


class RDAArchive:
    """RDA (.a7s / .a8s 外殻) の読取専用アーカイブ．

    Example:
        with RDAArchive(Path("sample.a7s")) as rda:
            for e in rda.entries:
                print(e.filename, e.uncompressed_size)
            data = rda.read("data.a7s")
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._stream: BinaryIO | None = None
        self._header: FileHeader | None = None
        self._entries: list[RDAEntry] | None = None

    # -------- context manager --------

    def __enter__(self) -> "RDAArchive":
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def open(self) -> None:
        """ファイルを開いて header と block chain を走査する．"""
        if self._stream is not None:
            return
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        self._stream = open(self.path, "rb")
        try:
            self._header = read_file_header(self._stream)
            self._entries = list(self._walk_blocks())
        except Exception:
            self._stream.close()
            self._stream = None
            raise

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    # -------- public API --------

    @property
    def header(self) -> FileHeader:
        self._ensure_open()
        assert self._header is not None
        return self._header

    @property
    def version(self) -> RDAVersion:
        return self.header.version

    @property
    def entries(self) -> list[RDAEntry]:
        """ブロックチェーン走査済みの全ファイルエントリ（順序保持）．"""
        self._ensure_open()
        assert self._entries is not None
        return list(self._entries)

    def entry_names(self) -> list[str]:
        return [e.filename for e in self.entries]

    def get_entry(self, filename: str) -> RDAEntry:
        """指定ファイル名のエントリを返す．重複時は最初のもの．"""
        for e in self.entries:
            if e.filename == filename:
                return e
        raise KeyError(filename)

    def read(self, filename: str) -> bytes:
        """指定ファイルを解凍済み bytes として返す．"""
        entry = self.get_entry(filename)
        return self._read_entry_data(entry)

    def extract(self, filename: str, dest: str | os.PathLike[str]) -> Path:
        """指定ファイルを dest へ書き出す．dest が既存ディレクトリなら同名で作成．"""
        entry = self.get_entry(filename)
        dest_path = Path(dest)
        if dest_path.is_dir():
            dest_path = dest_path / Path(filename).name
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        data = self._read_entry_data(entry)
        dest_path.write_bytes(data)
        return dest_path

    def extract_all(self, dest_dir: str | os.PathLike[str]) -> list[Path]:
        """全エントリを dest_dir 以下に書き出す．内部パス区切りは ``/``．"""
        dest_root = Path(dest_dir)
        dest_root.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for entry in self.entries:
            # filename にディレクトリが含まれる場合がある（例: "gfx/foo.bin"）
            safe_rel = entry.filename.replace("\\", "/").lstrip("/")
            out = dest_root / safe_rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(self._read_entry_data(entry))
            written.append(out)
        return written

    # -------- internal --------

    def _ensure_open(self) -> None:
        if self._stream is None or self._header is None:
            raise RuntimeError("RDAArchive is not open; use 'with' or call .open()")

    def _walk_blocks(self) -> Iterator[RDAEntry]:
        assert self._stream is not None and self._header is not None
        stream = self._stream
        version = self._header.version
        file_size = self.path.stat().st_size

        current = self._header.first_block_offset
        guard = 0
        while current < file_size:
            guard += 1
            if guard > 1_000_000:
                raise RDAParseError("block chain loop detected (>1M iterations)")

            stream.seek(current)
            block = read_block_info(stream, version)

            if block.is_deleted:
                current = block.next_block
                continue

            entries = read_directory(stream, current, block, version)
            for de in entries:
                yield _entry_from(de, block, version)

            current = block.next_block

    def _read_entry_data(self, entry: RDAEntry) -> bytes:
        self._ensure_open()
        assert self._stream is not None

        if entry.is_encrypted:
            raise EncryptedBlockError(
                "encrypted file data is not supported in v0.1.0"
            )

        self._stream.seek(entry.offset)
        raw = self._stream.read(entry.compressed_size)
        if len(raw) != entry.compressed_size:
            raise RDAParseError(
                f"unexpected EOF while reading {entry.filename!r} "
                f"(got {len(raw)}B, want {entry.compressed_size}B)"
            )
        if entry.is_compressed:
            try:
                raw = zlib.decompress(raw, bufsize=entry.uncompressed_size)
            except zlib.error as e:
                raise RDAParseError(
                    f"zlib decompress failed for {entry.filename!r}: {e}"
                ) from e
        return raw
