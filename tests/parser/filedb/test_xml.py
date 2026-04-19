"""xml.py のテスト．"""

from __future__ import annotations

import pytest
from lxml import etree

from anno_save_analyzer.parser.filedb import FileDBParseError, FileDBVersion, build_xml
from anno_save_analyzer.parser.filedb.dom import Attrib, Tag, Terminator
from anno_save_analyzer.parser.filedb.xml import _safe_name, build_xml_from_events

from .conftest import minimal_v3


class TestBuildXmlEndToEnd:
    def test_minimal_v3_tree_shape(self) -> None:
        blob = minimal_v3(
            tags={1: "Root", 2: "Child"},
            attribs={0x8001: "value"},
            events=[
                ("T", 1),
                ("T", 2),
                ("A", 0x8001, b"\xde\xad\xbe\xef"),
                ("X",),
                ("X",),
                ("X",),
            ],
        )
        root = build_xml(blob)
        assert root.tag == "FileDBDocument"
        # Root → Child → value
        root_tag = root[0]
        assert root_tag.tag == "Root"
        assert root_tag.get("id") == "1"
        child_tag = root_tag[0]
        assert child_tag.tag == "Child"
        value_attr = child_tag[0]
        assert value_attr.tag == "value"
        assert value_attr.get("hex") == "deadbeef"

    def test_build_xml_explicit_version_parameter(self) -> None:
        blob = minimal_v3(
            tags={1: "Only"},
            attribs={},
            events=[("T", 1), ("X",), ("X",)],
        )
        root = build_xml(blob, version=FileDBVersion.V3)
        assert root[0].tag == "Only"

    def test_build_xml_v1_unsupported(self) -> None:
        with pytest.raises(FileDBParseError, match="V1"):
            build_xml(b"\x00" * 32, version=FileDBVersion.V1)


class TestBuildXmlFromEvents:
    def test_root_level_terminator_is_noop(self) -> None:
        root = build_xml_from_events([Terminator()])
        assert root.tag == "FileDBDocument"
        assert len(root) == 0

    def test_unresolved_tag_name_falls_back(self) -> None:
        """tag_section 無しで名前未解決なら ``Tag_{id}`` フォールバック．"""
        root = build_xml_from_events([Tag(42), Terminator()])
        assert root[0].tag == "Tag_42"
        assert root[0].get("id") == "42"

    def test_unresolved_attrib_name_falls_back(self) -> None:
        root = build_xml_from_events([Tag(1, name="R"), Attrib(99, b"\x01"), Terminator()])
        r = root[0]
        assert r.tag == "R"
        assert r[0].tag == "Attrib_99"
        assert r[0].get("hex") == "01"


class TestSafeName:
    def test_none_falls_to_prefix(self) -> None:
        assert _safe_name(None, "Tag", 7) == "Tag_7"

    def test_empty_string_falls_to_prefix(self) -> None:
        assert _safe_name("", "Attrib", 3) == "Attrib_3"

    def test_special_chars_sanitized(self) -> None:
        assert _safe_name("foo.bar-baz", "Tag", 1) == "foo_bar_baz"

    def test_leading_digit_prefixed_with_underscore(self) -> None:
        assert _safe_name("1abc", "Tag", 1) == "_1abc"

    def test_all_special_chars_sanitized_to_underscores_keeps_leading_underscore(
        self,
    ) -> None:
        # "/" は全て `_` に置換 → "_" が残る．XML 名として有効な先頭．
        assert _safe_name("////", "Tag", 9) == "____"


class TestXmlSerialization:
    def test_tree_serializes_to_valid_xml(self) -> None:
        blob = minimal_v3(
            tags={1: "Sample"},
            attribs={0x8001: "note"},
            events=[("T", 1), ("A", 0x8001, b"\x00"), ("X",), ("X",)],
        )
        root = build_xml(blob)
        serialized = etree.tostring(root, pretty_print=True).decode()
        assert "<FileDBDocument>" in serialized
        assert "<Sample" in serialized
        assert 'hex="00"' in serialized
