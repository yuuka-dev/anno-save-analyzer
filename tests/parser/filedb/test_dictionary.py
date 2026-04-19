"""dictionary.py のテスト．"""

from __future__ import annotations

import struct

import pytest

from anno_save_analyzer.parser.filedb import (
    FileDBParseError,
    FileDBVersion,
    UnsupportedFileDBVersion,
    parse_tag_section,
)
from anno_save_analyzer.parser.filedb.dictionary import (
    TagDictionary,
    _parse_dictionary,
)

from .conftest import FileDBFixture, encode_dictionary, minimal_v3


class TestTagDictionary:
    def test_membership_and_lookup(self) -> None:
        d = TagDictionary(entries={1: "a", 2: "b"})
        assert 1 in d
        assert 99 not in d
        assert d[1] == "a"
        assert d.get(1) == "a"
        assert d.get(99) is None
        assert d.get(99, "fallback") == "fallback"
        assert len(d) == 2


class TestParseDictionaryHappy:
    def test_round_trip_minimal(self) -> None:
        data = encode_dictionary({1: "alpha", 2: "beta", 3: "gamma"})
        d = _parse_dictionary(data, 0)
        assert d.entries == {1: "alpha", 2: "beta", 3: "gamma"}

    def test_parse_tag_section_v3(self) -> None:
        blob = minimal_v3(
            tags={1: "Root"},
            attribs={0x8001: "x"},
            events=[("T", 1), ("A", 0x8001, b"\x01\x02\x03\x04"), ("X",)],
        )
        section = parse_tag_section(blob, FileDBVersion.V3)
        assert section.tags.entries == {1: "Root"}
        assert section.attribs.entries == {0x8001: "x"}


class TestParseDictionaryErrors:
    def test_negative_offset_raises(self) -> None:
        with pytest.raises(FileDBParseError, match="out of range"):
            _parse_dictionary(b"\x00" * 32, -1)

    def test_offset_past_end_raises(self) -> None:
        with pytest.raises(FileDBParseError, match="out of range"):
            _parse_dictionary(b"\x00" * 4, 100)

    def test_negative_count_raises(self) -> None:
        data = struct.pack("<i", -1)
        with pytest.raises(FileDBParseError, match="negative dictionary count"):
            _parse_dictionary(data, 0)

    def test_ids_past_eof_raises(self) -> None:
        # Count=5 だが IDs バイトが足りない
        data = struct.pack("<i", 5) + b"\x00\x01"
        with pytest.raises(FileDBParseError, match="extend past EOF"):
            _parse_dictionary(data, 0)

    def test_name_not_null_terminated(self) -> None:
        # Count=1, ID=1, 名前が null で終わらない
        data = struct.pack("<i", 1) + struct.pack("<H", 1) + b"abc"
        with pytest.raises(FileDBParseError, match="not null-terminated"):
            _parse_dictionary(data, 0)


class TestParseTagSectionErrors:
    def test_v1_unsupported(self) -> None:
        with pytest.raises(UnsupportedFileDBVersion):
            parse_tag_section(b"\x00" * 32, FileDBVersion.V1)

    def test_buffer_too_small(self) -> None:
        with pytest.raises(FileDBParseError, match="too small"):
            parse_tag_section(b"\x00" * 4, FileDBVersion.V3)

    def test_override_bad_offsets_raises(self) -> None:
        blob = FileDBFixture(
            tags={1: "Root"},
            attribs={0x8001: "x"},
            events=[("T", 1), ("X",)],
            override_tag_offset=999_999,
        ).build()
        with pytest.raises(FileDBParseError):
            parse_tag_section(blob, FileDBVersion.V3)
