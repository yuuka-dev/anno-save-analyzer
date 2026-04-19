"""trade.extract のテスト．"""

from __future__ import annotations

import zlib
from pathlib import Path

import pytest

from anno_save_analyzer.trade import GameTitle, ItemDictionary, extract
from anno_save_analyzer.trade.extract import _load_outer_filedb, normalise
from anno_save_analyzer.trade.interpreter.base import (
    ExtractionContext,
    RawTradedGoodTriple,
)

from .conftest import make_inner_filedb, wrap_as_outer


def _items_for_test(tmp_path: Path) -> ItemDictionary:
    title = "synth"
    en = tmp_path / f"items_{title}.en.yaml"
    en.write_text(
        "100:\n  name: Wood\n  category: raw\n200:\n  name: Bricks\n",
        encoding="utf-8",
    )
    return ItemDictionary.load(title, data_dir=tmp_path)


class TestNormalise:
    def test_passive_partner_set(self, tmp_path: Path) -> None:
        items = _items_for_test(tmp_path)
        raw = RawTradedGoodTriple(
            good_guid=100,
            amount=5,
            total_price=-50,
            context=ExtractionContext(
                session_id="0",
                partner_id="9001",
                partner_kind="passive",
            ),
        )
        ev = normalise(raw, items)
        assert ev.partner is not None
        assert ev.partner.id == "9001"
        assert ev.partner.kind == "passive"
        assert ev.route_id is None
        assert ev.item.display_name("en") == "Wood"

    def test_route_partner_synthesised(self, tmp_path: Path) -> None:
        items = _items_for_test(tmp_path)
        raw = RawTradedGoodTriple(
            good_guid=100,
            amount=1,
            total_price=0,
            context=ExtractionContext(
                session_id="0",
                route_id="42",
                partner_kind="route",
            ),
        )
        ev = normalise(raw, items)
        assert ev.partner is not None
        assert ev.partner.id == "route:42"
        assert ev.partner.kind == "route"
        assert ev.route_id == "42"

    def test_no_route_or_partner_keeps_partner_none(self, tmp_path: Path) -> None:
        items = _items_for_test(tmp_path)
        raw = RawTradedGoodTriple(
            good_guid=100,
            amount=0,
            total_price=0,
            context=ExtractionContext(session_id="0"),
        )
        ev = normalise(raw, items)
        assert ev.partner is None


class TestExtractE2E:
    def test_extract_from_bare_filedb(self, tmp_path: Path) -> None:
        inner = make_inner_filedb(
            {
                "route": [(7, 100, 5, 0), (7, 200, -3, 0)],
                "passive": [(99, 100, 1, -10)],
            }
        )
        outer = wrap_as_outer([inner])
        save = tmp_path / "fake.bin"
        save.write_bytes(outer)

        items = _items_for_test(tmp_path)
        events = list(extract(save, title=GameTitle.ANNO_117, items=items))

        assert len(events) == 3
        kinds = {ev.partner.kind for ev in events if ev.partner is not None}
        assert kinds == {"route", "passive"}

    def test_extract_handles_zlib_wrapped_bare(self, tmp_path: Path) -> None:
        inner = make_inner_filedb({"passive": [(1, 100, 1, 1)]})
        outer = wrap_as_outer([inner])
        save = tmp_path / "compressed.bin"
        save.write_bytes(zlib.compress(outer))

        items = _items_for_test(tmp_path)
        events = list(extract(save, title=GameTitle.ANNO_117, items=items))
        assert len(events) == 1


class TestLoadOuterFiledb:
    def test_bare_bin_returns_raw(self, tmp_path: Path) -> None:
        path = tmp_path / "x.bin"
        path.write_bytes(b"\x00\x01\x02")
        assert _load_outer_filedb(path) == b"\x00\x01\x02"

    def test_zlib_bin_is_decompressed(self, tmp_path: Path) -> None:
        payload = b"hello FileDB-ish payload"
        path = tmp_path / "z.bin"
        path.write_bytes(zlib.compress(payload))
        assert _load_outer_filedb(path) == payload

    def test_unknown_extension_with_invalid_zlib_magic_passthrough(self, tmp_path: Path) -> None:
        # 偶然先頭 2B が zlib magic 風になる場合の境界．`\x78\x01` を持つ非 zlib
        # データ（実際には valid な deflate data か検査される）．
        with pytest.raises(zlib.error):
            path = tmp_path / "y.bin"
            # \x78\x01 prefix だが続きが invalid → zlib.error が伝播
            path.write_bytes(b"\x78\x01\xff\xff\xff\xff")
            _load_outer_filedb(path)
