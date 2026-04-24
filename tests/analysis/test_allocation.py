"""``analysis.allocation.optimal_flow`` のテスト．

合成 balance_df で min-cost flow が期待どおり supplier → demander に
quantity を振り分けるか確認．
"""

from __future__ import annotations

import pandas as pd
import pytest

from anno_save_analyzer.analysis.allocation import optimal_flow


def _balance(rows: list[dict]) -> pd.DataFrame:
    defaults = {
        "city_name": None,
        "produced_per_minute": 0.0,
        "consumed_per_minute": 0.0,
        "is_deficit": False,
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


class TestOptimalFlow:
    def test_simple_supplier_to_demander(self) -> None:
        df = _balance(
            [
                {
                    "area_manager": "A",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": 3.0,
                },
                {
                    "area_manager": "B",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": -2.0,
                },
            ]
        )
        result = optimal_flow(df)
        assert len(result) == 1
        row = result.iloc[0]
        assert row["source_am"] == "A"
        assert row["sink_am"] == "B"
        # 需要 2.0 までしか流れない (supplier capacity 3.0 > demand 2.0)
        assert row["quantity_per_min"] == pytest.approx(2.0)

    def test_partial_flow_when_supply_lt_demand(self) -> None:
        df = _balance(
            [
                {
                    "area_manager": "A",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": 1.0,
                },
                {
                    "area_manager": "B",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": -5.0,
                },
            ]
        )
        result = optimal_flow(df)
        # supply 1 が全部 B に流れる (demand 5 は部分充足)
        assert result.iloc[0]["quantity_per_min"] == pytest.approx(1.0)

    def test_prefers_same_session_source(self) -> None:
        """距離 proxy を与えると同 session の supplier が優先される．"""
        df = _balance(
            [
                {
                    "area_manager": "A1",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": 5.0,
                },
                {
                    "area_manager": "A2",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": 5.0,
                },
                {
                    "area_manager": "B1",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": -3.0,
                },
            ]
        )
        session = {"A1": "old_world", "A2": "new_world", "B1": "old_world"}
        result = optimal_flow(df, session_by_area_manager=session)
        # A1 (same session) が優先される
        flow_a1 = result[result["source_am"] == "A1"]["quantity_per_min"].sum()
        flow_a2 = result[result["source_am"] == "A2"]["quantity_per_min"].sum()
        assert flow_a1 == pytest.approx(3.0)
        assert flow_a2 == pytest.approx(0.0)

    def test_multiple_products_solved_independently(self) -> None:
        df = _balance(
            [
                {
                    "area_manager": "A",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": 2.0,
                },
                {
                    "area_manager": "B",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": -1.0,
                },
                {
                    "area_manager": "A",
                    "product_guid": 200,
                    "product_name": "Bread",
                    "delta_per_minute": -3.0,
                },
                {
                    "area_manager": "B",
                    "product_guid": 200,
                    "product_name": "Bread",
                    "delta_per_minute": 4.0,
                },
            ]
        )
        result = optimal_flow(df)
        # Wood: A → B, Bread: B → A の 2 行
        by_product = {r["product_name"]: r for _, r in result.iterrows()}
        assert by_product["Wood"]["source_am"] == "A"
        assert by_product["Wood"]["sink_am"] == "B"
        assert by_product["Wood"]["quantity_per_min"] == pytest.approx(1.0)
        assert by_product["Bread"]["source_am"] == "B"
        assert by_product["Bread"]["sink_am"] == "A"
        assert by_product["Bread"]["quantity_per_min"] == pytest.approx(3.0)

    def test_no_supply_for_product_yields_no_flow(self) -> None:
        """赤字しかない物資は flow 生成されない．"""
        df = _balance(
            [
                {
                    "area_manager": "A",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": -1.0,
                },
                {
                    "area_manager": "B",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": -2.0,
                },
            ]
        )
        result = optimal_flow(df)
        assert result.empty

    def test_no_demand_for_product_yields_no_flow(self) -> None:
        """黒字しかない物資も flow 生成されない．"""
        df = _balance(
            [
                {
                    "area_manager": "A",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": 5.0,
                },
            ]
        )
        result = optimal_flow(df)
        assert result.empty

    def test_empty_input_returns_empty(self) -> None:
        result = optimal_flow(pd.DataFrame())
        assert result.empty
        assert list(result.columns) == [
            "product_guid",
            "product_name",
            "source_am",
            "sink_am",
            "quantity_per_min",
            "cost",
        ]


class TestEdgeCost:
    def test_cost_column_reflects_session_distance(self) -> None:
        df = _balance(
            [
                {
                    "area_manager": "A",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": 2.0,
                },
                {
                    "area_manager": "B",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": -1.0,
                },
            ]
        )
        # A,B は別 session
        result = optimal_flow(df, session_by_area_manager={"A": "x", "B": "y"})
        assert result.iloc[0]["cost"] == 10
        # 同 session
        result = optimal_flow(df, session_by_area_manager={"A": "x", "B": "x"})
        assert result.iloc[0]["cost"] == 1
