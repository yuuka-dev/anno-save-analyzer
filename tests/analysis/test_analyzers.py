"""B-G 各 analyzer の単体テスト．

``AnalysisFrames`` を合成データで作って pandas pivot / 相関 / 集計 /
分類 / 予測の各 module が正しく動くか確認する．
"""

from __future__ import annotations

import pandas as pd
import pytest

from anno_save_analyzer.analysis.correlation import saturation_vs_deficit
from anno_save_analyzer.analysis.deficit import deficit_heatmap, pareto
from anno_save_analyzer.analysis.forecast import (
    consumption_forecast,
    population_capacity_proxy,
)
from anno_save_analyzer.analysis.frames import AnalysisFrames
from anno_save_analyzer.analysis.persistence import classify_deficit
from anno_save_analyzer.analysis.routes import rank_routes
from anno_save_analyzer.analysis.sensitivity import route_leave_one_out
from anno_save_analyzer.trade.clock import TICKS_PER_MINUTE
from anno_save_analyzer.trade.storage import IslandStorageTrend, PointSeries

# ---------- fixtures ----------


def _balance_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "area_manager": "A1",
                "city_name": "岡山",
                "product_guid": 100,
                "product_name": "Wood",
                "produced_per_minute": 5.0,
                "consumed_per_minute": 2.0,
                "delta_per_minute": 3.0,
                "is_deficit": False,
            },
            {
                "area_manager": "A1",
                "city_name": "岡山",
                "product_guid": 200,
                "product_name": "Bread",
                "produced_per_minute": 1.0,
                "consumed_per_minute": 4.0,
                "delta_per_minute": -3.0,
                "is_deficit": True,
            },
            {
                "area_manager": "A2",
                "city_name": "広島",
                "product_guid": 100,
                "product_name": "Wood",
                "produced_per_minute": 2.0,
                "consumed_per_minute": 1.0,
                "delta_per_minute": 1.0,
                "is_deficit": False,
            },
            {
                "area_manager": "A2",
                "city_name": "広島",
                "product_guid": 200,
                "product_name": "Bread",
                "produced_per_minute": 0.5,
                "consumed_per_minute": 1.0,
                "delta_per_minute": -0.5,
                "is_deficit": True,
            },
        ]
    )


def _islands_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "area_manager": "A1",
                "city_name": "岡山",
                "is_player": True,
                "session_key": None,
                "session_display": None,
                "resident_total": 1000,
                "residence_count": 100,
                "avg_saturation_mean": 0.60,
                "deficit_count": 1,
            },
            {
                "area_manager": "A2",
                "city_name": "広島",
                "is_player": True,
                "session_key": None,
                "session_display": None,
                "resident_total": 500,
                "residence_count": 50,
                "avg_saturation_mean": 0.85,
                "deficit_count": 1,
            },
            {
                "area_manager": "A3",
                "city_name": "群馬",
                "is_player": True,
                "session_key": None,
                "session_display": None,
                "resident_total": 300,
                "residence_count": 30,
                "avg_saturation_mean": 0.95,
                "deficit_count": 0,
            },
        ]
    )


def _trade_events_df() -> pd.DataFrame:
    tp5 = 5 * TICKS_PER_MINUTE  # 5 min
    return pd.DataFrame(
        [
            {
                "timestamp_tick": pd.NA,
                "product_guid": 100,
                "product_name": "Wood",
                "amount": 10,
                "total_price": 100,
                "session_id": "0",
                "island_name": "岡山",
                "route_id": "route:1",
                "route_name": "R1",
                "partner_id": "route:1",
                "partner_kind": "route",
                "source_method": "history",
            },
            {
                "timestamp_tick": 0,
                "product_guid": 200,
                "product_name": "Bread",
                "amount": 5,
                "total_price": 50,
                "session_id": "0",
                "island_name": "岡山",
                "route_id": "route:1",
                "route_name": "R1",
                "partner_id": "route:1",
                "partner_kind": "route",
                "source_method": "history",
            },
            {
                "timestamp_tick": tp5,
                "product_guid": 100,
                "product_name": "Wood",
                "amount": 20,
                "total_price": 200,
                "session_id": "0",
                "island_name": "広島",
                "route_id": "route:2",
                "route_name": "R2",
                "partner_id": "route:2",
                "partner_kind": "route",
                "source_method": "history",
            },
        ]
    ).astype({"timestamp_tick": "Int64"})


def _frames() -> AnalysisFrames:
    return AnalysisFrames(
        islands=_islands_df(),
        tiers=pd.DataFrame(
            columns=[
                "area_manager",
                "city_name",
                "tier",
                "residence_count",
                "resident_total",
                "avg_saturation_mean",
            ]
        ),
        balance=_balance_df(),
        trade_events=_trade_events_df(),
    )


# ---------- B: deficit heatmap + Pareto ----------


class TestDeficitHeatmap:
    def test_pivot_island_by_product(self) -> None:
        heat = deficit_heatmap(_balance_df())
        assert set(heat.index) == {"A1", "A2"}
        assert set(heat.columns) == {"Wood", "Bread"}
        assert heat.loc["A1", "Bread"] == pytest.approx(-3.0)
        assert heat.loc["A2", "Wood"] == pytest.approx(1.0)

    def test_empty_input_returns_empty(self) -> None:
        heat = deficit_heatmap(pd.DataFrame())
        assert heat.empty


class TestPareto:
    def test_abc_rank_by_consumption(self) -> None:
        result = pareto(_balance_df(), metric="consumed_per_minute")
        # consumed: Wood=3.0 (2+1) / Bread=5.0 (4+1)．Bread が先
        assert result.iloc[0]["product_name"] == "Bread"
        assert result.iloc[1]["product_name"] == "Wood"
        # total=8.0．Bread=5.0/8=0.625 → A，Wood 累積 1.0 → C
        assert result.iloc[0]["abc_rank"] == "A"

    def test_empty_input_keeps_schema(self) -> None:
        result = pareto(pd.DataFrame())
        assert list(result.columns) == [
            "product_guid",
            "product_name",
            "consumed_per_minute",
            "cum_share",
            "abc_rank",
        ]

    def test_zero_total_returns_all_c(self) -> None:
        zero = _balance_df().copy()
        zero["consumed_per_minute"] = 0
        result = pareto(zero, metric="consumed_per_minute")
        assert (result["abc_rank"] == "C").all()


# ---------- C: correlation ----------


class TestCorrelation:
    def test_pearson_negative_when_deficit_hurts_saturation(self) -> None:
        # A1 avg_sat=0.60 と Bread delta=-3 (赤字), A2 avg_sat=0.85 と Bread delta=-0.5
        # Pearson r(sat, delta) = 正の相関 (赤字マシな方が満足度高い)
        # Wood: A1 delta=3 / A2 delta=1．正の関係 (多く生産する島ほど satisfaction 高い方向)
        # サンプル 2 なので `<3` で NaN になる
        result = saturation_vs_deficit(_frames())
        assert set(result["product_name"]) == {"Wood", "Bread"}
        # sample_size=2 なので NaN
        assert all(pd.isna(result["pearson_r"]))

    def test_sample_size_3_enables_correlation(self) -> None:
        """3 島以上あれば Pearson が計算される．"""
        balance_3islands = pd.DataFrame(
            [
                {
                    "area_manager": "A1",
                    "city_name": "A1",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "produced_per_minute": 0,
                    "consumed_per_minute": 0,
                    "delta_per_minute": -3.0,
                    "is_deficit": True,
                },
                {
                    "area_manager": "A2",
                    "city_name": "A2",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "produced_per_minute": 0,
                    "consumed_per_minute": 0,
                    "delta_per_minute": 0.0,
                    "is_deficit": False,
                },
                {
                    "area_manager": "A3",
                    "city_name": "A3",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "produced_per_minute": 0,
                    "consumed_per_minute": 0,
                    "delta_per_minute": 2.0,
                    "is_deficit": False,
                },
            ]
        )
        islands_3 = pd.DataFrame(
            [
                {"area_manager": "A1", "avg_saturation_mean": 0.3},
                {"area_manager": "A2", "avg_saturation_mean": 0.6},
                {"area_manager": "A3", "avg_saturation_mean": 0.9},
            ]
        )
        for col in [
            "city_name",
            "is_player",
            "session_key",
            "session_display",
            "resident_total",
            "residence_count",
            "deficit_count",
        ]:
            islands_3[col] = None
        frames = AnalysisFrames(
            islands=islands_3,
            tiers=pd.DataFrame(),
            balance=balance_3islands,
            trade_events=pd.DataFrame(),
        )
        result = saturation_vs_deficit(frames)
        row = result.iloc[0]
        assert row["sample_size"] == 3
        assert row["pearson_r"] == pytest.approx(1.0, abs=0.01)


# ---------- D: route ranking ----------


class TestRouteRanking:
    def test_groupby_route_with_per_minute_metric(self) -> None:
        result = rank_routes(_trade_events_df())
        by_route = result.set_index("route_id")
        assert "route:1" in by_route.index
        assert by_route.loc["route:1", "events_count"] == 2
        assert by_route.loc["route:1", "unique_products"] == 2

    def test_empty_returns_empty(self) -> None:
        result = rank_routes(pd.DataFrame())
        assert result.empty
        assert "tons_per_min" in result.columns


# ---------- E: persistence classify ----------


def _trend(product_guid: int, samples: tuple[int, ...]) -> IslandStorageTrend:
    return IslandStorageTrend(
        island_name="island",
        product_guid=product_guid,
        points=PointSeries(capacity=len(samples), size=len(samples), samples=samples),
    )


class TestPersistenceClassify:
    def test_chronic_when_many_zeros(self) -> None:
        samples = tuple([0] * 80 + [10] * 40)  # 66% zero
        result = classify_deficit({"岡山": [_trend(100, samples)]})
        assert result.iloc[0]["category"] == "chronic"

    def test_transient_when_some_zeros(self) -> None:
        samples = tuple([0] * 30 + [10] * 90)  # 25% zero
        result = classify_deficit({"岡山": [_trend(100, samples)]})
        assert result.iloc[0]["category"] == "transient"

    def test_stable_when_no_zeros(self) -> None:
        samples = tuple([50] * 120)
        result = classify_deficit({"岡山": [_trend(100, samples)]})
        assert result.iloc[0]["category"] == "stable"

    def test_empty_returns_empty(self) -> None:
        result = classify_deficit({})
        assert result.empty


# ---------- F: sensitivity (route leave-one-out) ----------


class TestRouteSensitivity:
    def test_leave_one_out_populates_rows(self) -> None:
        result = route_leave_one_out(_frames())
        # 2 route あり
        assert len(result) == 2
        assert "recommended_action" in result.columns

    def test_empty_events_returns_empty(self) -> None:
        empty = AnalysisFrames(
            islands=_islands_df(),
            tiers=pd.DataFrame(),
            balance=_balance_df(),
            trade_events=pd.DataFrame(
                columns=[
                    "timestamp_tick",
                    "product_guid",
                    "amount",
                    "route_id",
                    "route_name",
                    "total_price",
                ]
            ),
        )
        result = route_leave_one_out(empty)
        assert result.empty


# ---------- G: forecast ----------


class TestConsumptionForecast:
    def test_projected_total_scales_with_hours(self) -> None:
        result6h = consumption_forecast(_frames(), hours_ahead=6)
        result12h = consumption_forecast(_frames(), hours_ahead=12)
        # 12h は 6h の 2 倍
        bread6 = result6h[result6h["product_name"] == "Bread"].iloc[0]
        bread12 = result12h[result12h["product_name"] == "Bread"].iloc[0]
        assert bread12["projected_delta_total"] == pytest.approx(
            2 * bread6["projected_delta_total"]
        )

    def test_empty_balance_returns_empty(self) -> None:
        empty = AnalysisFrames(
            islands=pd.DataFrame(),
            tiers=pd.DataFrame(),
            balance=pd.DataFrame(),
            trade_events=pd.DataFrame(),
        )
        assert consumption_forecast(empty).empty


class TestPopulationCapacity:
    def test_headroom_calculation(self) -> None:
        result = population_capacity_proxy(_frames(), per_house=10)
        by_am = result.set_index("area_manager")
        # A1: 100 residences × 10 = 1000 capacity, 1000 resident = 0 headroom
        assert by_am.loc["A1", "headroom"] == 0
        assert by_am.loc["A1", "headroom_ratio"] == pytest.approx(0.0)
        # A3: 30 × 10 = 300, resident 300 → 0 headroom
        assert by_am.loc["A3", "headroom"] == 0
        # A2: 50 × 10 = 500, resident 500 → 0
        assert by_am.loc["A2", "headroom"] == 0

    def test_empty_islands_returns_empty(self) -> None:
        empty = AnalysisFrames(
            islands=pd.DataFrame(),
            tiers=pd.DataFrame(),
            balance=pd.DataFrame(),
            trade_events=pd.DataFrame(),
        )
        assert population_capacity_proxy(empty).empty
