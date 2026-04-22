"""RDA magic prefix 経由の extract dispatch テスト．

``load_outer_filedb`` は拡張子でなく先頭 magic で RDA / zlib / bare を振り分ける．
``extract_inner_filedb`` を monkeypatch で差し替えて RDA 分岐を踏ませる．
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

# trade.__init__ が extract 関数を同名で re-export しとるため，dotted import では
# function shadow が起きる．importlib で module 本体を取り出す．
extract_mod = importlib.import_module("anno_save_analyzer.trade.extract")


@pytest.mark.parametrize("suffix", [".a7s", ".a8s"])
def test_rda_magic_dispatches_to_pipeline(
    suffix: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``Resource File V2.`` prefix を持つバイトは RDA extract 経由で展開される．"""
    fake_save = tmp_path / f"fake{suffix}"
    # 実 RDA の magic 先頭のみ偽装．以降は extract_inner_filedb を mock で置き換え
    # して中身は見ないので残りはダミーで良い．
    fake_save.write_bytes(b"Resource File V2.2" + b"\x00" * 100)

    expected = b"<<<inner FileDB synthetic>>>"

    def _fake_extract(_path: object) -> bytes:
        return expected

    monkeypatch.setattr(extract_mod, "extract_inner_filedb", _fake_extract)
    assert extract_mod.load_outer_filedb(fake_save) == expected


def test_non_rda_falls_back_to_raw_bytes(tmp_path: Path) -> None:
    """RDA magic が無ければ bare FileDB バイナリとしてそのまま返す．

    テスト fixture / 手動展開済ファイルでも通るように．
    """
    fake_save = tmp_path / "fake.a8s"
    fake_save.write_bytes(b"not a real RDA")
    assert extract_mod.load_outer_filedb(fake_save) == b"not a real RDA"
