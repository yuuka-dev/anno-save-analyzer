"""Anno 1800 実セーブでの Factory7 抽出 smoke test．

書記長の ``sample_anno1800.a7s`` から全 session の工場を舐めて，件数と
productivity の分布が実在ゲームの値に収まっていることを確認する．

しきい値 (session 数 / 工場総数) は書記長の canonical sample を前提にしており，
他 save に差し替えると fail する可能性が高い．sample 無しなら skip．
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anno_save_analyzer.parser.filedb import detect_version, parse_tag_section
from anno_save_analyzer.parser.filedb.session import extract_sessions
from anno_save_analyzer.parser.pipeline import extract_inner_filedb
from anno_save_analyzer.trade.factories import list_factory_aggregates

SAMPLE_PATH = Path(__file__).resolve().parents[2] / "sample_anno1800.a7s"
_HAS_SAMPLE = SAMPLE_PATH.is_file()


@pytest.mark.skipif(not _HAS_SAMPLE, reason=f"Anno 1800 sample not found: {SAMPLE_PATH}")
class TestAnno1800FactoriesSmoke:
    @pytest.fixture(scope="class")
    def aggregates_per_session(self) -> list[list]:
        outer = extract_inner_filedb(SAMPLE_PATH)
        ver = detect_version(outer)
        sec = parse_tag_section(outer, ver)
        sessions = list(extract_sessions(outer, ver, sec))
        return [list(list_factory_aggregates(inner)) for inner in sessions]

    def test_sessions_extracted(self, aggregates_per_session: list[list]) -> None:
        """Anno 1800 の save は 5 session (Cape Trelawney / Old World / Enbesa /
        New World / Arctic)．抽出 pipeline が何 session か返す．"""
        assert len(aggregates_per_session) == 5

    def test_at_least_one_session_has_factories(self, aggregates_per_session: list[list]) -> None:
        """書記長の save は Arctic 以外は必ず工場がある．1 session 以上で 100+
        工場が取れる想定 (DLC 込みで主要島は 100-500 工場)．"""
        counts = [sum(a.total for a in session_aggs) for session_aggs in aggregates_per_session]
        assert max(counts) >= 100, f"no session has enough factories: {counts}"

    def test_productivity_is_non_negative_and_finite(
        self, aggregates_per_session: list[list]
    ) -> None:
        """CurrentProductivity は 0 以上で常識的な範囲に収まる．DLC のアイテム
        で 200% を超えるケースも実在 (書記長 save で 300% 実測) するため上限は
        緩めに 10.0 で wall．i32 誤読が入ると巨大値 / 負値になるため型確定の
        ガードになる．"""
        import math

        for session_aggs in aggregates_per_session:
            for agg in session_aggs:
                for inst in agg.instances:
                    p = inst.productivity
                    assert math.isfinite(p), f"non-finite productivity: {p}"
                    assert 0.0 <= p <= 10.0, (
                        f"productivity out of [0,10]: {p} "
                        f"(AM={agg.area_manager}, guid={inst.building_guid})"
                    )

    def test_building_guids_are_positive_ints(self, aggregates_per_session: list[list]) -> None:
        """guid attrib が正しく i32 decode されとるか．負値は decode 失敗の兆候．"""
        for session_aggs in aggregates_per_session:
            for agg in session_aggs:
                for inst in agg.instances:
                    assert inst.building_guid > 0, (
                        f"non-positive guid: {inst.building_guid} (AM={agg.area_manager})"
                    )

    def test_total_factories_across_sessions(self, aggregates_per_session: list[list]) -> None:
        """書記長の save は DLC 込みで全 session 合計 500+ 工場想定．"""
        total = sum(sum(a.total for a in session_aggs) for session_aggs in aggregates_per_session)
        assert total >= 500, f"unexpectedly few factories in total: {total}"
