"""``.a7s`` / ``.a8s`` 拡張子経由の extract 動作テスト．

実 RDA を組み立てるのは大掛かりなため，``extract_inner_filedb`` を monkeypatch
で差し替えて ``load_outer_filedb`` の suffix branch（line 77）を踏ませる．
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

# trade.__init__ が extract 関数を同名で re-export しとるため，dotted import では
# function shadow が起きる．importlib で module 本体を取り出す．
extract_mod = importlib.import_module("anno_save_analyzer.trade.extract")


@pytest.mark.parametrize("suffix", [".a7s", ".a8s"])
def test_a7s_a8s_suffix_dispatches_to_pipeline(
    suffix: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_save = tmp_path / f"fake{suffix}"
    fake_save.write_bytes(b"not a real RDA")

    expected = b"<<<inner FileDB synthetic>>>"

    def _fake_extract(_path: object) -> bytes:
        return expected

    monkeypatch.setattr(extract_mod, "extract_inner_filedb", _fake_extract)
    assert extract_mod.load_outer_filedb(fake_save) == expected
