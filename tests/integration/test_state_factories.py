"""``TuiState.factories_by_island`` が save 経由で正しく組み立てられるかの結合試験．

Anno 1800 の本物 sample (``sample_anno1800.a7s``) があれば実データで factories
の存在確認と出力 GUID の妥当性をチェック．無ければ skip．
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anno_save_analyzer.trade.factory_recipes import FactoryRecipeTable
from anno_save_analyzer.trade.models import GameTitle
from anno_save_analyzer.tui.state import load_state

SAMPLE = Path(__file__).resolve().parents[2] / "sample_anno1800.a7s"
_HAS_SAMPLE = SAMPLE.is_file()


@pytest.mark.integration
@pytest.mark.skipif(not _HAS_SAMPLE, reason=f"Anno 1800 sample not found: {SAMPLE}")
class TestFactoriesByIsland:
    @pytest.fixture(scope="class")
    def state(self):
        return load_state(SAMPLE, title=GameTitle.ANNO_1800, locale="en")

    def test_factories_present(self, state) -> None:
        """書記長 save には複数島に factory aggregate がある．"""
        assert len(state.factories_by_island) >= 5

    def test_factory_instances_have_known_recipe(self, state) -> None:
        """大半の building_guid は ``FactoryRecipeTable`` で解決可能．

        書記長の save には Calculator 由来の YAML に未登録な mod 工場は
        基本無いはず (DLC 工場は YAML に含まれる)．未登録率が極端に高い場合
        recipe loader か抽出側のリグレッションを示す．
        """
        recipes = FactoryRecipeTable.load()
        all_guids: set[int] = set()
        unknown = 0
        for agg in state.factories_by_island.values():
            for inst in agg.instances:
                all_guids.add(inst.building_guid)
                if inst.building_guid not in recipes:
                    unknown += 1
        assert all_guids, "no factory instances found"
        # 未登録 instance 比率は 50% 未満．これより高ければ recipe テーブル
        # 側の問題か，extraction の guid 取り違えが疑われる．
        total = sum(len(agg.instances) for agg in state.factories_by_island.values())
        assert unknown / total < 0.5

    def test_island_keys_match_supply_balance_when_player(self, state) -> None:
        """プレイヤー島は supply_balance の area_manager_to_city と同じキーで
        参照できる．Tree filter (session > island) と factories_by_island の整合．
        """
        for am, city in state.area_manager_to_city.items():
            # AreaManager に対応する factories は city_name キーで保持される
            # (NPC は AreaManager_N キー)．プレイヤー島で factory が無いケース
            # (純住居島) もあるので存在 assertion はしない．キー存在確認のみ．
            if am in {agg.area_manager for agg in state.factories_by_island.values()}:
                # 同じ city_name でも引けるはず (NPC でない限り)．
                assert city in state.factories_by_island or am in state.factories_by_island
