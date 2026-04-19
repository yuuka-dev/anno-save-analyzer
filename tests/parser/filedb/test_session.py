"""session.py のテスト．

SessionData/BinaryData が再帰 FileDB であることを実地で確認した上で，
外側 DOM からの抽出ロジックを合成フィクスチャで検証する．
"""

from __future__ import annotations

import struct

import pytest

from anno_save_analyzer.parser.filedb import (
    FileDBParseError,
    FileDBVersion,
    PlayerIsland,
    detect_version,
    extract_sessions,
    list_inner_area_managers,
    list_player_islands,
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


class TestListInnerAreaManagers:
    def test_extracts_numeric_suffix_in_ascending_order(self) -> None:
        inner = minimal_v3(
            tags={
                2: "AreaManager_257",
                3: "AreaManager_1",
                4: "AreaManager_64",
                5: "OtherTag",
                6: "AreaManager_NonNumeric",  # suffix not digit → ignored
            },
            attribs={},
            events=[("T", 2), ("X",)],
        )
        ids = list_inner_area_managers(inner)
        assert ids == (1, 64, 257)

    def test_empty_session_returns_empty_tuple(self) -> None:
        assert list_inner_area_managers(b"") == ()

    def test_no_area_manager_tags_returns_empty(self) -> None:
        inner = minimal_v3(
            tags={2: "Other", 3: "AnotherTag"},
            attribs={},
            events=[("T", 2), ("X",)],
        )
        assert list_inner_area_managers(inner) == ()


class TestListPlayerIslands:
    """``CityName`` attrib 持ち AreaInfo > <1> エントリを抽出．"""

    def test_returns_named_islands_only(self) -> None:
        # AreaInfo > <1> 3 件．うち 2 件に CityName，1 件は CityNameGuid のみ
        inner = minimal_v3(
            tags={2: "AreaInfo"},
            attribs={
                0x8001: "CityName",
                0x8002: "CityNameGuid",
            },
            events=[
                ("T", 2),  # AreaInfo
                # entry 0: CityName 持ち = プレイヤー命名
                ("T", 1),
                ("A", 0x8001, "大阪民国".encode("utf-16-le")),
                ("X",),
                # entry 1: CityNameGuid のみ = NPC
                ("T", 1),
                ("A", 0x8002, struct.pack("<i", 999)),
                ("X",),
                # entry 2: CityName 持ち
                ("T", 1),
                ("A", 0x8001, "ジョウト地方".encode("utf-16-le")),
                ("X",),
                ("X",),  # close AreaInfo
            ],
        )
        islands = list_player_islands(inner)
        assert len(islands) == 2
        assert islands[0] == PlayerIsland(city_name="大阪民国")
        assert islands[1] == PlayerIsland(city_name="ジョウト地方")

    def test_empty_session_returns_empty(self) -> None:
        assert list_player_islands(b"") == ()

    def test_no_area_info_tag_returns_empty(self) -> None:
        inner = minimal_v3(
            tags={2: "Other"},
            attribs={},
            events=[("T", 2), ("X",)],
        )
        assert list_player_islands(inner) == ()

    def test_strips_trailing_null_from_city_name(self) -> None:
        inner = minimal_v3(
            tags={2: "AreaInfo"},
            attribs={0x8001: "CityName"},
            events=[
                ("T", 2),
                ("T", 1),
                # 末尾 null padding
                ("A", 0x8001, "島".encode("utf-16-le") + b"\x00\x00\x00\x00"),
                ("X",),
                ("X",),
            ],
        )
        islands = list_player_islands(inner)
        assert islands == (PlayerIsland(city_name="島"),)

    def test_nested_tag_inside_area_info_entry_does_not_break_walk(self) -> None:
        """AreaInfo > <1> の中に更に nested tag がある場合，OPEN 時の depth>+1 分岐を踏む．"""
        inner = minimal_v3(
            tags={2: "AreaInfo", 3: "Sub"},
            attribs={0x8001: "CityName", 0x8002: "Other"},
            events=[
                ("T", 2),  # AreaInfo
                ("T", 1),  # entry
                ("A", 0x8001, "深い島".encode("utf-16-le")),
                ("T", 3),  # nested Sub
                ("A", 0x8002, b"\x01\x02"),
                ("X",),  # close Sub
                ("X",),  # close entry
                ("X",),  # close AreaInfo
            ],
        )
        islands = list_player_islands(inner)
        assert islands == (PlayerIsland(city_name="深い島"),)

    def test_root_level_terminator_skipped(self) -> None:
        """iter_dom が DOM 終端で吐く余分 terminator を `_iter_player_islands` 側でも安全に skip．"""
        # AreaInfo タグはあるが entry 無し，余分 terminator 1 個．
        inner = minimal_v3(
            tags={2: "AreaInfo"},
            attribs={},
            events=[("T", 2), ("X",), ("X",)],
        )
        assert list_player_islands(inner) == ()
