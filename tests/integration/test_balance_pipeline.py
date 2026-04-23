"""supply balance の end-to-end pipeline 結合試験．

save → sessions → factories + residences (+ tier) → balance table を実
sample で通し，複数島の supply/demand が実データでつながることを確認する．
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anno_save_analyzer.parser.filedb import detect_version, parse_tag_section
from anno_save_analyzer.parser.filedb.session import extract_sessions
from anno_save_analyzer.parser.pipeline import extract_inner_filedb
from anno_save_analyzer.trade.balance import build_balance_table
from anno_save_analyzer.trade.buildings import BuildingDictionary
from anno_save_analyzer.trade.consumption import ConsumptionTable
from anno_save_analyzer.trade.factories import list_factory_aggregates
from anno_save_analyzer.trade.factory_recipes import FactoryRecipeTable
from anno_save_analyzer.trade.population import list_residence_aggregates

SAMPLE = Path(__file__).resolve().parents[2] / "sample_anno1800.a7s"
_HAS_SAMPLE = SAMPLE.is_file()


@pytest.mark.integration
@pytest.mark.skipif(not _HAS_SAMPLE, reason=f"Anno 1800 sample not found: {SAMPLE}")
class TestSupplyBalancePipeline:
    @pytest.fixture(scope="class")
    def balance(self):
        outer = extract_inner_filedb(SAMPLE)
        ver = detect_version(outer)
        sec = parse_tag_section(outer, ver)
        buildings = BuildingDictionary.load()
        consumption = ConsumptionTable.load()
        recipes = FactoryRecipeTable.load()

        all_residences = []
        all_factories = []
        for inner in extract_sessions(outer, ver, sec):
            all_residences.extend(list_residence_aggregates(inner, buildings=buildings))
            all_factories.extend(list_factory_aggregates(inner))
        return build_balance_table(
            residences=all_residences,
            factories=all_factories,
            recipes=recipes,
            consumption=consumption,
        )

    def test_islands_populated(self, balance) -> None:
        assert len(balance.islands) >= 10

    def test_some_products_appear(self, balance) -> None:
        """少なくとも 1 島に 1 product balance がある．"""
        with_products = [isl for isl in balance.islands if isl.products]
        assert len(with_products) >= 1

    def test_some_islands_have_production_and_consumption(self, balance) -> None:
        """書記長 save の主要島には生産と消費の両方が出るはず．"""
        has_produce = False
        has_consume = False
        for isl in balance.islands:
            for p in isl.products:
                if p.produced_per_minute > 0:
                    has_produce = True
                if p.consumed_per_minute > 0:
                    has_consume = True
        assert has_produce, "no island produced any good"
        assert has_consume, "no island consumed any good"

    def test_aggregate_is_invariant_with_respect_to_sum(self, balance) -> None:
        """全島集計の produced/consumed 合計 = 個別島の合計．"""
        combined = balance.aggregate()
        for p in combined.products:
            total_produced = sum(
                pp.produced_per_minute
                for isl in balance.islands
                for pp in isl.products
                if pp.product_guid == p.product_guid
            )
            total_consumed = sum(
                pp.consumed_per_minute
                for isl in balance.islands
                for pp in isl.products
                if pp.product_guid == p.product_guid
            )
            assert p.produced_per_minute == pytest.approx(total_produced)
            assert p.consumed_per_minute == pytest.approx(total_consumed)

    def test_fish_balance_is_meaningful(self, balance) -> None:
        """Fish (1010200) は Farmer 消費の代表品目．書記長の 17+ 島には
        Fishery 複数あるはずで，少なくとも 1 島で produced > 0．"""
        any_fish_produced = any(
            p.produced_per_minute > 0
            for isl in balance.islands
            for p in isl.products
            if p.product_guid == 1010200
        )
        any_fish_consumed = any(
            p.consumed_per_minute > 0
            for isl in balance.islands
            for p in isl.products
            if p.product_guid == 1010200
        )
        assert any_fish_produced, "no Fishery producing Fish (1010200) in save"
        assert any_fish_consumed, "no island consuming Fish (1010200) in save"
