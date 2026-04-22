"""trade.sessions のテスト．"""

from __future__ import annotations

from anno_save_analyzer.trade.models import GameTitle
from anno_save_analyzer.trade.sessions import (
    SESSION_KEYS,
    session_key_for,
    session_locale_key,
)


class TestSessionKeyFor:
    def test_returns_latium_for_anno117_index_0(self) -> None:
        assert session_key_for(GameTitle.ANNO_117, 0) == "latium"

    def test_returns_albion_for_anno117_index_1(self) -> None:
        assert session_key_for(GameTitle.ANNO_117, 1) == "albion"

    def test_returns_cape_trelawney_for_anno1800_index_0(self) -> None:
        # 実セーブで観測した順序 (Ubisoft 内部 asset ID 順っぽい)
        assert session_key_for(GameTitle.ANNO_1800, 0) == "cape_trelawney"

    def test_anno1800_full_order(self) -> None:
        # 書記長 2026-04-22 報告で修正した順序を固定
        assert SESSION_KEYS[GameTitle.ANNO_1800] == (
            "cape_trelawney",
            "old_world",
            "enbesa",
            "new_world",
            "arctic",
        )

    def test_returns_none_for_out_of_range_index(self) -> None:
        assert session_key_for(GameTitle.ANNO_117, 99) is None

    def test_returns_none_for_negative_index(self) -> None:
        assert session_key_for(GameTitle.ANNO_117, -1) is None


class TestSessionLocaleKey:
    def test_anno117_latium(self) -> None:
        assert session_locale_key(GameTitle.ANNO_117, 0) == "session.anno117.latium"

    def test_anno1800_arctic_at_index_4(self) -> None:
        # 実セーブ起点順序では末尾は Arctic
        assert session_locale_key(GameTitle.ANNO_1800, 4) == "session.anno1800.arctic"

    def test_unknown_index_falls_back_to_unknown(self) -> None:
        assert session_locale_key(GameTitle.ANNO_117, 99) == "session.unknown"


class TestSessionKeysSchema:
    def test_anno117_has_two_sessions(self) -> None:
        assert len(SESSION_KEYS[GameTitle.ANNO_117]) == 2

    def test_anno1800_has_five_sessions(self) -> None:
        assert len(SESSION_KEYS[GameTitle.ANNO_1800]) == 5
