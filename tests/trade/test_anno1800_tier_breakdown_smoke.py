"""Anno 1800 実セーブでの Residence tier breakdown smoke test．

書記長の ``sample_anno1800.a7s`` + packaged ``buildings_anno1800.en.yaml``
を使って ``list_residence_aggregates(buildings=...)`` が実データで意味ある
tier 分解を返すことを確認する．
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anno_save_analyzer.parser.filedb import detect_version, parse_tag_section
from anno_save_analyzer.parser.filedb.session import extract_sessions
from anno_save_analyzer.parser.pipeline import extract_inner_filedb
from anno_save_analyzer.trade.buildings import BuildingDictionary
from anno_save_analyzer.trade.population import list_residence_aggregates

SAMPLE_PATH = Path(__file__).resolve().parents[2] / "sample_anno1800.a7s"
_HAS_SAMPLE = SAMPLE_PATH.is_file()


@pytest.mark.skipif(not _HAS_SAMPLE, reason=f"Anno 1800 sample not found: {SAMPLE_PATH}")
class TestAnno1800TierBreakdownSmoke:
    @pytest.fixture(scope="class")
    def aggregates(self) -> list:
        """packaged buildings を使って全 session の ResidenceAggregate を集める．"""
        buildings = BuildingDictionary.load()
        outer = extract_inner_filedb(SAMPLE_PATH)
        ver = detect_version(outer)
        sec = parse_tag_section(outer, ver)
        out = []
        for inner in extract_sessions(outer, ver, sec):
            out.extend(list_residence_aggregates(inner, buildings=buildings))
        return out

    def test_aggregates_populated(self, aggregates: list) -> None:
        """書記長 save は 17+ 島 (Arctic 除く) で residence がある．"""
        populated = [a for a in aggregates if a.residence_count > 0]
        assert len(populated) >= 10

    def test_tier_breakdown_populated_when_buildings_given(self, aggregates: list) -> None:
        """buildings を与えると tier_breakdown が空でなくなる．"""
        with_breakdown = [a for a in aggregates if a.tier_breakdown]
        assert len(with_breakdown) >= 10

    def test_known_tier_appears_in_breakdown(self, aggregates: list) -> None:
        """主要 tier (farmer / worker / artisan / engineer / investor) の少なくとも
        どれかが実 save で抽出される．tier 判定ロジックが死んでないかのガード．"""
        all_tiers: set[str] = set()
        for agg in aggregates:
            for ts in agg.tier_breakdown:
                all_tiers.add(ts.tier)
        known = {"farmer", "worker", "artisan", "engineer", "investor"}
        assert all_tiers & known, f"no known tier found: {sorted(all_tiers)}"

    def test_tier_resident_totals_sum_to_aggregate(self, aggregates: list) -> None:
        """tier_breakdown の ``resident_total`` 合計は島全体の ``resident_total``
        と一致する．invariant がずれたら集計バグ．"""
        for agg in aggregates:
            if not agg.tier_breakdown:
                continue
            tier_sum = sum(ts.resident_total for ts in agg.tier_breakdown)
            assert tier_sum == agg.resident_total, (
                f"tier sum {tier_sum} != island total {agg.resident_total} for {agg.area_manager}"
            )

    def test_tier_residence_counts_sum_to_aggregate(self, aggregates: list) -> None:
        """residence_count も同様に invariant．"""
        for agg in aggregates:
            if not agg.tier_breakdown:
                continue
            tier_sum = sum(ts.residence_count for ts in agg.tier_breakdown)
            assert tier_sum == agg.residence_count, (
                f"tier residence sum {tier_sum} != island total {agg.residence_count} "
                f"for {agg.area_manager}"
            )
