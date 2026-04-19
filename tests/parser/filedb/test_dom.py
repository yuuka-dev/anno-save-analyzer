"""dom.py のテスト．"""

from __future__ import annotations

import struct

import pytest

from anno_save_analyzer.parser.filedb import (
    Attrib,
    DomEvent,
    EventKind,
    FileDBParseError,
    FileDBVersion,
    Tag,
    Terminator,
    iter_dom,
    parse_tag_section,
)
from anno_save_analyzer.parser.filedb.dom import _block_space

from .conftest import FileDBFixture, minimal_v3


class TestBlockSpace:
    @pytest.mark.parametrize(
        "bytesize, block, expected",
        [
            (0, 8, 0),
            (1, 8, 8),
            (8, 8, 8),
            (9, 8, 16),
            (16, 8, 16),
            (5, 0, 5),  # V1 は padding 無し
            (-3, 8, 0),  # 負数はゼロに潰す（防御）
        ],
    )
    def test_block_space(self, bytesize: int, block: int, expected: int) -> None:
        assert _block_space(bytesize, block) == expected


class TestIterDomHappyPaths:
    def test_minimal_v3_roundtrip(self) -> None:
        blob = minimal_v3(
            tags={1: "Root", 2: "Child"},
            attribs={0x8001: "x", 0x8002: "y"},
            events=[
                ("T", 1),
                ("A", 0x8001, b"\xaa\xbb"),
                ("T", 2),
                ("A", 0x8002, b"\x01\x02\x03\x04"),
                ("X",),  # close Child
                ("X",),  # close Root
                ("X",),  # DOM terminator
            ],
        )
        section = parse_tag_section(blob, FileDBVersion.V3)
        events = list(iter_dom(blob, FileDBVersion.V3, tag_section=section))

        kinds = [(e.kind, e.id_, e.name) for e in events]
        assert kinds == [
            (EventKind.TAG, 1, "Root"),
            (EventKind.ATTRIB, 0x8001, "x"),
            (EventKind.TAG, 2, "Child"),
            (EventKind.ATTRIB, 0x8002, "y"),
            (EventKind.TERMINATOR, 0, None),
            (EventKind.TERMINATOR, 0, None),
            (EventKind.TERMINATOR, 0, None),
        ]
        # Attrib の content
        attrib_events = [e for e in events if e.kind is EventKind.ATTRIB]
        assert attrib_events[0].content == b"\xaa\xbb"
        assert attrib_events[1].content == b"\x01\x02\x03\x04"

    def test_iter_dom_without_tag_section_leaves_names_none(self) -> None:
        blob = minimal_v3(
            tags={1: "Root"},
            attribs={0x8001: "x"},
            events=[("T", 1), ("A", 0x8001, b"\x00"), ("X",)],
        )
        events = list(iter_dom(blob, FileDBVersion.V3))
        assert all(ev.name is None for ev in events)

    def test_iter_dom_with_explicit_dom_end(self) -> None:
        blob = minimal_v3(
            tags={1: "Root"},
            attribs={},
            events=[("T", 1), ("X",)],
        )
        # dom_end=0 は空 DOM — 何も yield しない．
        events = list(iter_dom(blob, FileDBVersion.V3, dom_end=0))
        assert events == []

    def test_attrib_content_padding_applied(self) -> None:
        """V3 で 3 バイトの content は disk 上 8 バイト（パディング済）になる．"""
        content = b"\x11\x22\x33"
        blob = minimal_v3(
            tags={1: "R"},
            attribs={0x8001: "a"},
            events=[("T", 1), ("A", 0x8001, content), ("X",)],
        )
        events = list(iter_dom(blob, FileDBVersion.V3))
        attrib_ev = next(e for e in events if e.kind is EventKind.ATTRIB)
        # 正味 content は 3 バイトだが，次の terminator が正しく読めることで padding 境界正確性を確認
        assert attrib_ev.content == content
        terminators = [e for e in events if e.kind is EventKind.TERMINATOR]
        assert len(terminators) == 1


class TestDomEventProperties:
    def test_tag_factory_and_flags(self) -> None:
        t = Tag(5, name="Foo")
        assert t.is_tag and not t.is_attrib and not t.is_terminator
        assert t.id_ == 5 and t.name == "Foo"

    def test_attrib_factory_and_flags(self) -> None:
        a = Attrib(0x8001, b"\x00\x01")
        assert a.is_attrib and not a.is_tag and not a.is_terminator
        assert a.content == b"\x00\x01"

    def test_terminator_factory(self) -> None:
        x = Terminator()
        assert x.is_terminator and not x.is_tag and not x.is_attrib
        assert x.id_ == 0

    def test_direct_construction_via_dataclass(self) -> None:
        ev = DomEvent(kind=EventKind.TAG, id_=7)
        assert ev.id_ == 7
        assert ev.name is None
        assert ev.content == b""


class TestIterDomErrors:
    def test_buffer_too_small(self) -> None:
        with pytest.raises(FileDBParseError, match="too small"):
            list(iter_dom(b"\x00" * 4, FileDBVersion.V3))

    def test_tags_offset_out_of_bounds(self) -> None:
        # 小さいバッファに TagsOffset=負数を埋めて OOB 発火
        blob = bytearray(b"\x00" * 32)
        # offset ペア + magic の位置 (末尾 16B) に負の TagsOffset を書く
        struct.pack_into("<ii", blob, len(blob) - 16, -1, 0)
        with pytest.raises(FileDBParseError, match="TagsOffset"):
            list(iter_dom(bytes(blob), FileDBVersion.V3))

    def test_eof_in_dom_header(self) -> None:
        """DOM 途中で 4 バイトだけ残して header の 8 バイトが読めないケース．"""
        blob = FileDBFixture(
            tags={1: "R"},
            attribs={},
            # わざと 1 件だけ event を詰め，そのあと 4 バイトのゴミを挟んでから dict へ
            events=[("T", 1), ("X",)],
        ).build()
        # TagsOffset が DOM + 4B のゴミを含むように手で調整する: DOM 長 + 4
        import struct as _s

        ts_offset_pos = len(blob) - 16
        original_ts_offset = _s.unpack_from("<i", blob, ts_offset_pos)[0]
        new_blob = bytearray(blob)
        # DOM と dict の間に 4 バイトゴミを挿入
        new_blob[original_ts_offset:original_ts_offset] = b"\xff\xff\xff\xff"
        # offset をずらす
        _s.pack_into(
            "<ii",
            new_blob,
            ts_offset_pos + 4,
            original_ts_offset + 4,
            _s.unpack_from("<i", blob, ts_offset_pos + 4)[0] + 4,
        )
        with pytest.raises(FileDBParseError, match="unexpected EOF"):
            list(iter_dom(bytes(new_blob), FileDBVersion.V3))

    def test_attrib_content_overruns_dom_end(self) -> None:
        """Attrib bytesize が DOM 残量より大きい場合のエラー．"""
        # TagsOffset を DOM 開始直後に強制設定．attrib header の 8B は読めるが content が超過
        blob = FileDBFixture(
            tags={1: "R"},
            attribs={0x8001: "x"},
            events=[("A", 0x8001, b"\x00" * 64)],
            override_tag_offset=8,  # DOM=8B (header のみ) とする．content 64B は超過
        ).build()
        with pytest.raises(FileDBParseError, match="past DOM end"):
            list(iter_dom(blob, FileDBVersion.V3))

    def test_too_many_terminators(self) -> None:
        """Tag を開かずに Terminator 連発 → depth < -1 で例外．"""
        blob = minimal_v3(
            tags={},
            attribs={},
            events=[("X",), ("X",), ("X",)],
        )
        with pytest.raises(FileDBParseError, match="more Terminators"):
            list(iter_dom(blob, FileDBVersion.V3))
