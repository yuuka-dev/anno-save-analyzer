"""version.py のテスト．"""

from __future__ import annotations

import pytest

from anno_save_analyzer.parser.filedb import FileDBVersion, UnsupportedFileDBVersion
from anno_save_analyzer.parser.filedb.exceptions import FileDBParseError
from anno_save_analyzer.parser.filedb.version import (
    _MAGIC_V2,
    _MAGIC_V3,
    detect_version,
    magic_bytes,
)


class TestDetectVersion:
    def test_v2_magic_detected(self) -> None:
        data = b"\x00" * 24 + _MAGIC_V2
        assert detect_version(data) is FileDBVersion.V2

    def test_v3_magic_detected(self) -> None:
        data = b"\x00" * 24 + _MAGIC_V3
        assert detect_version(data) is FileDBVersion.V3

    def test_no_match_falls_back_to_v1(self) -> None:
        """マッチしない末尾は V1 扱い．上流 ``VersionDetector`` と同じ挙動．"""
        data = b"\xde\xad\xbe\xef" * 4
        assert detect_version(data) is FileDBVersion.V1

    def test_memoryview_input(self) -> None:
        data = memoryview(b"\x00" * 16 + _MAGIC_V3)
        assert detect_version(data) is FileDBVersion.V3

    def test_too_short_raises(self) -> None:
        with pytest.raises(FileDBParseError, match="too small"):
            detect_version(b"\x00\x01\x02")


class TestMagicBytesAndVersion:
    def test_magic_bytes_v2(self) -> None:
        assert magic_bytes(FileDBVersion.V2) == _MAGIC_V2

    def test_magic_bytes_v3(self) -> None:
        assert magic_bytes(FileDBVersion.V3) == _MAGIC_V3

    def test_magic_bytes_v1_is_none(self) -> None:
        assert magic_bytes(FileDBVersion.V1) is None

    def test_offset_to_offsets_v2_v3_is_16(self) -> None:
        assert FileDBVersion.V2.offset_to_offsets == 16
        assert FileDBVersion.V3.offset_to_offsets == 16

    def test_offset_to_offsets_v1_is_4(self) -> None:
        assert FileDBVersion.V1.offset_to_offsets == 4

    def test_block_size(self) -> None:
        assert FileDBVersion.V1.block_size == 0
        assert FileDBVersion.V2.block_size == 8
        assert FileDBVersion.V3.block_size == 8

    def test_uses_attrib_blocks(self) -> None:
        assert FileDBVersion.V3.uses_attrib_blocks
        assert FileDBVersion.V2.uses_attrib_blocks
        assert not FileDBVersion.V1.uses_attrib_blocks

    def test_unsupported_version_type(self) -> None:
        # UnsupportedFileDBVersion は FileDBParseError のサブクラス．
        assert issubclass(UnsupportedFileDBVersion, FileDBParseError)
