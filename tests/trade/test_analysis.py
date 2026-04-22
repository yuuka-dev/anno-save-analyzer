"""trade.analysis の単体テスト．"""

from __future__ import annotations

from anno_save_analyzer.trade.analysis import (
    IslandProductRunway,
    compute_runways,
    display_runway_rows,
    shortage_list,
    supply_demand_balance,
)
from anno_save_analyzer.trade.models import Item
from anno_save_analyzer.trade.storage import IslandStorageTrend, PointSeries


def _trend(island: str, guid: int, samples: tuple[int, ...]) -> IslandStorageTrend:
    n = len(samples)
    return IslandStorageTrend(
        island_name=island,
        product_guid=guid,
        points=PointSeries(capacity=n, size=n, samples=samples),
    )


class TestIslandProductRunway:
    def test_depleted_zero(self) -> None:
        r = IslandProductRunway(island_name="A", product_guid=1, latest=0, slope_per_min=-1.0)
        assert r.runway_min == 0.0
        assert r.status == "depleted"

    def test_growing_none(self) -> None:
        r = IslandProductRunway(island_name="A", product_guid=1, latest=100, slope_per_min=1.0)
        assert r.runway_min is None
        assert r.status == "stable_or_growing"

    def test_declining(self) -> None:
        # 100 units, losing 2/min → 50 min runway
        r = IslandProductRunway(island_name="A", product_guid=1, latest=100, slope_per_min=-2.0)
        assert r.runway_min == 50.0
        assert r.status == "warning"  # 10 <= 50 < 60

    def test_critical_under_10min(self) -> None:
        r = IslandProductRunway(island_name="A", product_guid=1, latest=5, slope_per_min=-1.0)
        assert r.runway_min == 5.0
        assert r.status == "critical"

    def test_ok_over_60min(self) -> None:
        r = IslandProductRunway(island_name="A", product_guid=1, latest=1000, slope_per_min=-1.0)
        assert r.runway_min == 1000.0
        assert r.status == "ok"


class TestComputeRunways:
    def test_sorted_by_runway_ascending(self) -> None:
        trends = [
            _trend("A", 1, (100, 99, 98)),  # slope = -1 → runway 98
            _trend("B", 2, (50, 48, 46)),  # slope = -2 → runway 23
            _trend("C", 3, (10, 20, 30)),  # growing → None
            _trend("D", 4, (5, 4, 3)),  # slope = -1 → runway 3
        ]
        rws = compute_runways(trends)
        assert [r.island_name for r in rws] == ["D", "B", "A", "C"]
        # C は None で末尾
        assert rws[-1].runway_min is None

    def test_empty(self) -> None:
        assert compute_runways([]) == []


class TestShortageList:
    def test_filters_by_threshold(self) -> None:
        trends = [
            _trend("A", 1, (10, 9, 8)),  # slope = -1, runway 8
            _trend("B", 2, (100, 99, 98)),  # slope = -1, runway 98
            _trend("C", 3, (1000, 999, 998)),  # slope = -1, runway 998 (ok)
        ]
        # threshold 120: A (8) と B (98) は不足，C (998) は OK
        result = shortage_list(trends, threshold_min=120.0)
        assert len(result) == 2
        assert result[0].island_name == "A"
        assert result[1].island_name == "B"

    def test_threshold_none_returns_all_negative_slope(self) -> None:
        trends = [
            _trend("A", 1, (10, 9, 8)),
            _trend("B", 2, (10, 20, 30)),  # growing → not in shortage
        ]
        result = shortage_list(trends, threshold_min=None)
        assert len(result) == 1
        assert result[0].island_name == "A"


class TestSupplyDemandBalance:
    def test_splits_surplus_and_deficit_by_slope_sign(self) -> None:
        trends = [
            _trend("A", 1, (10, 20, 30)),  # A 生産 (slope +10)
            _trend("B", 1, (30, 20, 10)),  # B 消費 (slope -10)
            _trend("C", 1, (5, 5, 5)),  # C 平坦 (slope 0)
        ]
        balances = supply_demand_balance(trends)
        assert len(balances) == 1
        b = balances[0]
        assert b.product_guid == 1
        assert b.surplus_islands == ("A",)
        assert b.deficit_islands == ("B",)
        # net = +10 + (-10) + 0 = 0
        assert b.net_slope_per_min == 0.0

    def test_sorted_by_net_descending(self) -> None:
        trends = [
            # good 1: net positive
            _trend("A", 1, (10, 20, 30)),
            # good 2: net negative
            _trend("A", 2, (30, 20, 10)),
        ]
        balances = supply_demand_balance(trends)
        assert [b.product_guid for b in balances] == [1, 2]


class TestDisplayRunwayRows:
    def test_renders_dict_rows(self) -> None:
        rw = IslandProductRunway(
            island_name="大阪民国", product_guid=2135, latest=5, slope_per_min=-1.0
        )
        items = {2135: Item(guid=2135, names={"en": "Iron", "ja": "鉄"})}
        rows = display_runway_rows([rw], items, locale="ja")
        assert len(rows) == 1
        r = rows[0]
        assert r["island_name"] == "大阪民国"
        assert r["product_name"] == "鉄"
        assert r["runway_min"] == 5.0
        assert r["status"] == "critical"

    def test_missing_item_falls_back(self) -> None:
        rw = IslandProductRunway(island_name="X", product_guid=9999, latest=10, slope_per_min=-1.0)
        rows = display_runway_rows([rw], {}, locale="en")
        # KeyError → fallback Good_9999
        assert rows[0]["product_name"] == "Good_9999"

    def test_none_runway_passes_through(self) -> None:
        rw = IslandProductRunway(island_name="X", product_guid=1, latest=10, slope_per_min=1.0)
        items = {1: Item(guid=1, names={"en": "X"})}
        rows = display_runway_rows([rw], items)
        assert rows[0]["runway_min"] is None
