"""trade.extract の追加テスト：zlib magic 全 variant + .a8s ルート．"""

from __future__ import annotations

import zlib
from pathlib import Path

from anno_save_analyzer.trade.extract import _load_outer_filedb


class TestZlibMagicVariants:
    def test_zlib_magic_78_da(self, tmp_path: Path) -> None:
        # 高圧縮レベルの zlib magic = 78 da
        payload = b"x" * 100
        compressed = zlib.compress(payload, level=9)
        assert compressed[:2] == b"\x78\xda"
        path = tmp_path / "z9.bin"
        path.write_bytes(compressed)
        assert _load_outer_filedb(path) == payload

    def test_zlib_magic_78_9c(self, tmp_path: Path) -> None:
        # 標準圧縮 (level=6) の magic = 78 9c
        payload = b"y" * 100
        compressed = zlib.compress(payload, level=6)
        assert compressed[:2] == b"\x78\x9c"
        path = tmp_path / "z6.bin"
        path.write_bytes(compressed)
        assert _load_outer_filedb(path) == payload

    def test_zlib_magic_78_01(self, tmp_path: Path) -> None:
        # 無圧縮レベルの magic = 78 01
        payload = b"z" * 100
        compressed = zlib.compress(payload, level=1)
        assert compressed[:2] == b"\x78\x01"
        path = tmp_path / "z1.bin"
        path.write_bytes(compressed)
        assert _load_outer_filedb(path) == payload
