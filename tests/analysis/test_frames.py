"""``analysis.frames.to_frames`` のテスト．

pandas DataFrame 4 本が正しく構築されるかと，title 非依存性 (Anno 117 /
balance 無し) が保たれるかを確認する．
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from anno_save_analyzer.analysis import to_frames
from anno_save_analyzer.trade.balance import (
    IslandBalance,
    ProductBalance,
    SupplyBalanceTable,
)
from anno_save_analyzer.trade.models import GameTitle
from anno_save_analyzer.trade.population import (
    ProductSaturation,
    ResidenceAggregate,
    TierSummary,
)
from anno_save_analyzer.tui.state import TuiState

# ---------- fixtures ----------


def _mk_balance_table() -> SupplyBalanceTable:
    return SupplyBalanceTable(
        islands=(
            IslandBalance(
                area_manager="AreaManager_1",
                city_name="岡山",
                resident_total=1000,
                products=(
                    ProductBalance(
                        product_guid=200, produced_per_minute=4.0, consumed_per_minute=1.5
                    ),
                    ProductBalance(
                        product_guid=300, produced_per_minute=0.5, consumed_per_minute=2.0
                    ),
                ),
            ),
            IslandBalance(
                area_manager="AreaManager_2",
                city_name=None,
                resident_total=500,
                products=(
                    ProductBalance(
                        product_guid=200, produced_per_minute=2.0, consumed_per_minute=1.0
                    ),
                ),
            ),
        )
    )


def _inject_balance(state: TuiState) -> TuiState:
    """既存 tui_state fixture (Anno 117) に Anno 1800 の balance を追加差し込み．"""
    return dataclasses.replace(
        state,
        title=GameTitle.ANNO_1800,
        balance_table=_mk_balance_table(),
        area_manager_to_session_key={
            "AreaManager_1": "session.anno1800.old_world",
            "AreaManager_2": "session.anno1800.cape_trelawney",
        },
        area_manager_to_city={"AreaManager_1": "岡山"},
        population_by_city={
            "岡山": ResidenceAggregate(
                area_manager="AreaManager_1",
                residence_count=100,
                resident_total=1000,
                avg_saturation_mean=0.7,
                product_saturations=(
                    ProductSaturation(product_guid=200, current=0.9, average=0.85),
                ),
                tier_breakdown=(
                    TierSummary(
                        tier="farmer",
                        residence_count=60,
                        resident_total=600,
                        avg_saturation_mean=0.8,
                    ),
                    TierSummary(
                        tier="worker",
                        residence_count=40,
                        resident_total=400,
                        avg_saturation_mean=0.55,
                    ),
                ),
            ),
        },
    )


# ---------- Islands DataFrame ----------


class TestIslandsFrame:
    def test_one_row_per_island(self, tui_state) -> None:
        state = _inject_balance(tui_state)
        frames = to_frames(state)
        assert len(frames.islands) == 2

    def test_columns_schema(self, tui_state) -> None:
        state = _inject_balance(tui_state)
        frames = to_frames(state)
        expected = {
            "area_manager",
            "city_name",
            "is_player",
            "session_key",
            "session_display",
            "resident_total",
            "residence_count",
            "avg_saturation_mean",
            "deficit_count",
        }
        assert set(frames.islands.columns) == expected

    def test_player_vs_npc_flag(self, tui_state) -> None:
        state = _inject_balance(tui_state)
        frames = to_frames(state)
        by_am = frames.islands.set_index("area_manager")
        assert (
            by_am.loc["AreaManager_1", "is_player"] is True
            or by_am.loc["AreaManager_1", "is_player"]
        )
        assert not by_am.loc["AreaManager_2", "is_player"]

    def test_session_display_resolved(self, tui_state) -> None:
        """Localizer で session_key → display 解決されてる．"""
        state = _inject_balance(tui_state)
        frames = to_frames(state)
        displays = set(frames.islands["session_display"].dropna())
        # 旧世界 / トレローニー岬 (ja locale) or Old World / Cape Trelawney (en)
        assert any("Old World" in d or "旧世界" in d for d in displays)

    def test_deficit_count(self, tui_state) -> None:
        state = _inject_balance(tui_state)
        frames = to_frames(state)
        by_am = frames.islands.set_index("area_manager")
        # AreaManager_1: product 300 で deficit (0.5 vs 2.0)
        assert by_am.loc["AreaManager_1", "deficit_count"] == 1
        # AreaManager_2: 黒字のみ
        assert by_am.loc["AreaManager_2", "deficit_count"] == 0


# ---------- Tiers DataFrame ----------


class TestTiersFrame:
    def test_tier_rows_per_island(self, tui_state) -> None:
        state = _inject_balance(tui_state)
        frames = to_frames(state)
        # AreaManager_1 に farmer + worker 2 tier
        assert len(frames.tiers) == 2

    def test_residents_per_tier(self, tui_state) -> None:
        state = _inject_balance(tui_state)
        frames = to_frames(state)
        by_tier = frames.tiers.set_index("tier")
        assert by_tier.loc["farmer", "resident_total"] == 600
        assert by_tier.loc["worker", "resident_total"] == 400


# ---------- Balance DataFrame ----------


class TestBalanceFrame:
    def test_rows_per_island_product(self, tui_state) -> None:
        state = _inject_balance(tui_state)
        frames = to_frames(state)
        # AreaManager_1: 2 product, AreaManager_2: 1 product
        assert len(frames.balance) == 3

    def test_delta_column(self, tui_state) -> None:
        state = _inject_balance(tui_state)
        frames = to_frames(state)
        # AreaManager_1 product 300 は delta = 0.5 - 2.0 = -1.5
        mask = (frames.balance["area_manager"] == "AreaManager_1") & (
            frames.balance["product_guid"] == 300
        )
        row = frames.balance[mask].iloc[0]
        assert row["delta_per_minute"] == pytest.approx(-1.5)
        assert bool(row["is_deficit"]) is True


# ---------- TradeEvents DataFrame ----------


class TestTradeEventsFrame:
    def test_columns_include_route_and_partner(self, tui_state) -> None:
        frames = to_frames(tui_state)
        expected = {
            "timestamp_tick",
            "product_guid",
            "product_name",
            "amount",
            "total_price",
            "session_id",
            "island_name",
            "route_id",
            "route_name",
            "partner_id",
            "partner_kind",
            "source_method",
        }
        assert set(frames.trade_events.columns) == expected

    def test_has_events(self, tui_state) -> None:
        frames = to_frames(tui_state)
        # tui_state fixture は複数 TradeEvent を含む合成 save
        assert len(frames.trade_events) > 0

    def test_timestamp_tick_is_nullable_int(self, tui_state) -> None:
        frames = to_frames(tui_state)
        if not frames.trade_events.empty:
            # pandas の Int64 拡張型が使われてる (nullable)
            assert str(frames.trade_events["timestamp_tick"].dtype) == "Int64"


# ---------- title 非依存 (Anno 117 / balance 無し) ----------


class TestTitleAgnostic:
    def test_anno117_no_balance_yields_empty_schema(self, tui_state) -> None:
        """Anno 117 fixture (balance_table=None) でも DataFrame schema は維持．"""
        # tui_state fixture そのまま Anno 117
        frames = to_frames(tui_state)
        assert list(frames.islands.columns) == [
            "area_manager",
            "city_name",
            "is_player",
            "session_key",
            "session_display",
            "resident_total",
            "residence_count",
            "avg_saturation_mean",
            "deficit_count",
        ]
        # balance_table=None なので islands は空
        assert frames.islands.empty
        # balance も空
        assert frames.balance.empty

    def test_empty_inputs_keep_columns(self, tmp_path: Path, tui_state) -> None:
        """空 state でも DataFrame が crash せず空を返す．"""
        state = dataclasses.replace(tui_state, events=(), population_by_city={}, balance_table=None)
        frames = to_frames(state)
        assert frames.islands.empty
        assert frames.tiers.empty
        assert frames.balance.empty
        assert frames.trade_events.empty


# ---------- conftest ---------

# tui_state fixture は tests/tui/conftest.py で定義．analysis は TUI に依存
# しないため，test 用にそちらの fixture を流用する conftest を用意．
