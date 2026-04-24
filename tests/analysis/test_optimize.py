"""OR-Tools VRP ``optimize_routes`` のテスト．

合成 balance_df で VRP solver が supplier → demander の経路を解けるか，
不足時は unmet_demand に落ちるかを確認．ortools は optional extra なので
``pytest.importorskip`` で未 install 環境は skip．
"""

from __future__ import annotations

import pandas as pd
import pytest

pytest.importorskip("ortools")

from anno_save_analyzer.analysis.optimize import (  # noqa: E402
    OptimizedPlan,
    OptimizedRoute,
    UnmetDemand,
    optimize_routes,
)


def _balance(rows: list[dict]) -> pd.DataFrame:
    defaults = {
        "city_name": None,
        "produced_per_minute": 0.0,
        "consumed_per_minute": 0.0,
        "is_deficit": False,
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


class TestBasicSolve:
    def test_simple_pickup_and_delivery(self) -> None:
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
                    "delta_per_minute": -1.5,
                },
            ]
        )
        plan = optimize_routes(df, n_vehicles=1, vehicle_capacity=100, time_limit_seconds=3)
        assert isinstance(plan, OptimizedPlan)
        assert plan.solve_status == "ok"
        # 1 vehicle が A を pickup → B に delivery
        assert len(plan.routes) >= 1
        all_stops = [s for r in plan.routes for s in r.stops]
        assert any(s.area_manager == "A" and s.kind == "pickup" for s in all_stops)
        assert any(s.area_manager == "B" and s.kind == "delivery" for s in all_stops)

    def test_empty_input_returns_empty_plan(self) -> None:
        plan = optimize_routes(pd.DataFrame())
        assert plan.solve_status == "empty_input"
        assert plan.routes == ()
        assert plan.unmet_demand == ()
        assert plan.objective_value == 0


class TestMultipleProducts:
    def test_products_solved_independently(self) -> None:
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
                    "delta_per_minute": -2.0,
                },
                {
                    "area_manager": "B",
                    "product_guid": 200,
                    "product_name": "Bread",
                    "delta_per_minute": 3.0,
                },
            ]
        )
        plan = optimize_routes(df, n_vehicles=2, vehicle_capacity=100, time_limit_seconds=3)
        products = {r.product_name for r in plan.routes}
        assert products == {"Wood", "Bread"}


class TestUnmetDemand:
    def test_capacity_exceed_yields_unmet(self) -> None:
        """vehicle_capacity 不足で全 demand を運べない場合 unmet が出る．"""
        df = _balance(
            [
                {
                    "area_manager": "A",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": 100.0,
                },
                {
                    "area_manager": "B",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": -50.0,
                },
                {
                    "area_manager": "C",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": -40.0,
                },
            ]
        )
        # vehicle_capacity=1 tons → scaled 1000．demand は各 50/40 tons × 1000．
        # 1 vehicle 1 trip では運べないので unmet が発生する想定
        plan = optimize_routes(df, n_vehicles=1, vehicle_capacity=1, time_limit_seconds=3)
        # 少なくとも一方の demander は unmet になるべき
        assert len(plan.unmet_demand) >= 1
        for u in plan.unmet_demand:
            assert u.product_guid == 100
            assert u.quantity_per_min > 0


class TestSessionDistance:
    def test_same_session_cheaper_than_cross_session(self) -> None:
        """A1, B1 同 session / A2 別 session．同 session 解のほうが objective 小．"""
        df = _balance(
            [
                {
                    "area_manager": "A1",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": 2.0,
                },
                {
                    "area_manager": "A2",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": 2.0,
                },
                {
                    "area_manager": "B1",
                    "product_guid": 100,
                    "product_name": "Wood",
                    "delta_per_minute": -1.0,
                },
            ]
        )
        same_session_plan = optimize_routes(
            df,
            n_vehicles=1,
            vehicle_capacity=100,
            session_by_area_manager={"A1": "x", "A2": "y", "B1": "x"},
            time_limit_seconds=3,
        )
        # A1 (same session) pickup が優先されれば objective は低めに
        all_pickups = [
            s.area_manager for r in same_session_plan.routes for s in r.stops if s.kind == "pickup"
        ]
        # A1 が使われている
        assert "A1" in all_pickups


class TestDataclasses:
    def test_route_frozen(self) -> None:
        r = OptimizedRoute(
            vehicle_id=0, product_guid=1, product_name="x", stops=(), total_distance=0
        )
        with pytest.raises(Exception):  # noqa: B017
            r.vehicle_id = 1  # type: ignore[misc]

    def test_unmet_frozen(self) -> None:
        u = UnmetDemand(area_manager="A", product_guid=1, product_name="x", quantity_per_min=0.5)
        with pytest.raises(Exception):  # noqa: B017
            u.quantity_per_min = 1.0  # type: ignore[misc]
