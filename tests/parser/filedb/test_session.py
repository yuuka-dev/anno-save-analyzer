"""session.py のテスト．

SessionData/BinaryData が再帰 FileDB であることを実地で確認した上で，
外側 DOM からの抽出ロジックを合成フィクスチャで検証する．
"""

from __future__ import annotations

import pytest

from anno_save_analyzer.parser.filedb import (
    FileDBParseError,
    FileDBVersion,
    detect_version,
    extract_sessions,
    parse_tag_section,
)

from .conftest import minimal_v3


def _wrap_inner_filedb_as_session_blob(inner: bytes) -> bytes:
    """inner を BinaryData attrib として <SessionData> タグに包んだ外側 FileDB を合成．"""
    return minimal_v3(
        tags={1: "SessionData", 2: "Ignored"},
        attribs={0x8001: "BinaryData", 0x8002: "other"},
        events=[
            # 無関係な BinaryData（session 外）
            ("A", 0x8001, b"\xca\xfe"),
            # 1 つ目の SessionData 配下
            ("T", 1),
            ("A", 0x8001, inner),
            ("X",),
            # 2 つ目の SessionData（空 BinaryData で複数件を検証）
            ("T", 1),
            ("A", 0x8001, b""),
            ("X",),
            # 別の tag 内の BinaryData（抽出されないこと）
            ("T", 2),
            ("A", 0x8001, b"\x00\x01\x02"),
            ("X",),
        ],
    )


class TestExtractSessionsHappy:
    def test_extracts_only_session_scoped_binary_attribs(self) -> None:
        inner_data = b"\x01\x02\x03\x04" * 32
        outer = _wrap_inner_filedb_as_session_blob(inner_data)
        sessions = extract_sessions(outer)
        assert sessions == [inner_data, b""]

    def test_accepts_precomputed_version_and_section(self) -> None:
        inner_data = b"\xaa" * 16
        outer = _wrap_inner_filedb_as_session_blob(inner_data)
        version = detect_version(outer)
        section = parse_tag_section(outer, version)
        sessions = extract_sessions(outer, version=version, tag_section=section)
        assert sessions == [inner_data, b""]


class TestExtractSessionsErrors:
    def test_raises_when_dictionary_lacks_names(self) -> None:
        """SessionData / BinaryData 名が辞書に無い外側 FileDB は扱えない．"""
        outer = minimal_v3(
            tags={1: "Other"},
            attribs={0x8001: "NotBinary"},
            events=[("T", 1), ("A", 0x8001, b"\x00"), ("X",)],
        )
        with pytest.raises(FileDBParseError, match="SessionData"):
            extract_sessions(outer)

    def test_unsupported_outer_version_raises(self) -> None:
        """外側が V1 だと tag section が parse 不可のため FileDBParseError が連鎖する．"""
        with pytest.raises(FileDBParseError):
            extract_sessions(b"\x00" * 32, version=FileDBVersion.V1)
