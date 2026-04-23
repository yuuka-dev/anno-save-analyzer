"""trade.population の単体テスト．

Residence7 walk と Jaccard 割当 の両方を合成 FileDB + 手書き signature で
検証する．
"""

from __future__ import annotations

import struct

import pytest

from anno_save_analyzer.trade.buildings import BuildingDictionary, BuildingEntry
from anno_save_analyzer.trade.population import (
    CityAreaMatch,
    ResidenceAggregate,
    _confidence_label,
    build_am_consumption_signatures,
    list_residence_aggregates,
    match_cities_to_area_managers,
)
from tests.parser.filedb.conftest import Event, minimal_v3


def _f32_bytes(v: float) -> bytes:
    return struct.pack("<f", v)


def _i32_bytes(v: int) -> bytes:
    return struct.pack("<i", v)


def _build_am_with_residences(
    am_tag_name: str = "AreaManager_8771",
    residences: list[dict] | None = None,
) -> bytes:
    """合成 FileDB で 1 つの AreaManager に複数 Residence7 を配置．

    ``residences`` の各要素:
      ``{resident_count: int, product_money: int, avg_saturation: float,
         consumption: [(guid, current, avg), ...]}``
    """
    residences = residences or []
    tags = {
        2: am_tag_name,
        3: "Residence7",
        4: "ConsumptionStates",
    }
    attribs = {
        0x8001: "ResidentCount",
        0x8002: "ProductMoneyOutput",
        0x8003: "NewspaperMoneyOutput",
        0x8004: "AverageNeedSaturation",
        0x8005: "CurrentSaturation",
        0x8006: "AverageSaturation",
    }
    events: list[Event] = [("T", 2)]  # AreaManager_<N>
    for r in residences:
        events.append(("T", 3))  # Residence7
        events.append(("A", 0x8001, _i32_bytes(r.get("resident_count", 0))))
        events.append(("A", 0x8002, _i32_bytes(r.get("product_money", 0))))
        events.append(("A", 0x8003, _i32_bytes(r.get("newspaper_money", 0))))
        events.append(("A", 0x8004, _f32_bytes(r.get("avg_saturation", 0.0))))
        events.append(("T", 4))  # ConsumptionStates
        for guid, cur, avg in r.get("consumption", []):
            events.append(("A", 0x8FFF, _i32_bytes(guid)))
            events.append(("T", 1))  # <1>
            events.append(("A", 0x8005, _f32_bytes(cur)))
            events.append(("A", 0x8006, _f32_bytes(avg)))
            events.append(("X",))  # close <1>
        events.append(("X",))  # close ConsumptionStates
        events.append(("X",))  # close Residence7
    events.append(("X",))  # close AreaManager_<N>
    return minimal_v3(tags=tags, attribs=attribs, events=events)


class TestListResidenceAggregates:
    def test_empty_bytes_returns_empty(self) -> None:
        assert list_residence_aggregates(b"") == ()

    def test_no_residence7_returns_empty(self) -> None:
        buf = minimal_v3(tags={2: "AreaManager_1"}, attribs={}, events=[("T", 2), ("X",)])
        assert list_residence_aggregates(buf) == ()

    def test_aggregates_resident_totals_per_am(self) -> None:
        buf = _build_am_with_residences(
            residences=[
                {"resident_count": 10, "product_money": 5, "avg_saturation": 0.5},
                {"resident_count": 20, "product_money": 8, "avg_saturation": 0.8},
            ]
        )
        out = list_residence_aggregates(buf)
        assert len(out) == 1
        agg = out[0]
        assert agg.area_manager == "AreaManager_8771"
        assert agg.residence_count == 2
        assert agg.resident_total == 30
        assert agg.product_money_total == 13
        # residents-weighted mean of saturations: (10*0.5 + 20*0.8) / 30 = 0.7
        assert agg.avg_saturation_mean == pytest.approx(0.7)

    def test_product_saturations_averaged_across_residences(self) -> None:
        buf = _build_am_with_residences(
            residences=[
                {
                    "resident_count": 10,
                    "consumption": [(1010566, 1.0, 0.9), (1010257, 0.5, 0.6)],
                },
                {
                    "resident_count": 20,
                    "consumption": [(1010566, 0.8, 0.85), (1010257, 0.4, 0.5)],
                },
            ]
        )
        out = list_residence_aggregates(buf)
        sats = {s.product_guid: s for s in out[0].product_saturations}
        # 2 residences each contribute once → simple arithmetic mean
        assert sats[1010566].current == pytest.approx(0.9)
        assert sats[1010566].average == pytest.approx(0.875)
        assert sats[1010257].current == pytest.approx(0.45)
        assert sats[1010257].average == pytest.approx(0.55)

    def test_consumption_entry_without_saturation_excluded(self) -> None:
        """ConsumptionStates に登録はあるが CurrentSaturation/AverageSaturation 属性が
        付いてない entry は signature から除外される (jaccard 精度のため)．"""
        tags = {2: "AreaManager_1", 3: "Residence7", 4: "ConsumptionStates"}
        attribs = {
            0x8001: "ResidentCount",
            0x8005: "CurrentSaturation",
        }
        events: list[Event] = [
            ("T", 2),
            ("T", 3),
            ("A", 0x8001, _i32_bytes(10)),
            ("T", 4),
            # entry 1: no saturation attribs → excluded
            ("A", 0x8FFF, _i32_bytes(111)),
            ("T", 1),
            ("X",),
            # entry 2: saturation present → included
            ("A", 0x8FFF, _i32_bytes(222)),
            ("T", 1),
            ("A", 0x8005, _f32_bytes(0.9)),
            ("X",),
            ("X",),  # close ConsumptionStates
            ("X",),  # close Residence7
            ("X",),  # close AreaManager_1
        ]
        buf = minimal_v3(tags=tags, attribs=attribs, events=events)
        out = list_residence_aggregates(buf)
        sats = {s.product_guid for s in out[0].product_saturations}
        assert sats == {222}


class TestResidenceAggregateDerived:
    def test_residents_per_residence(self) -> None:
        a = ResidenceAggregate(area_manager="X", residence_count=4, resident_total=40)
        assert a.residents_per_residence == 10.0

    def test_gold_per_resident(self) -> None:
        a = ResidenceAggregate(
            area_manager="X",
            residence_count=1,
            resident_total=100,
            product_money_total=200,
            newspaper_money_total=50,
        )
        assert a.gold_per_resident == 2.5

    def test_zero_residents_no_division_by_zero(self) -> None:
        a = ResidenceAggregate(area_manager="X")
        assert a.residents_per_residence == 0.0
        assert a.gold_per_resident == 0.0


class TestMatchCitiesToAreaManagers:
    def test_empty_cities_returns_empty(self) -> None:
        assert match_cities_to_area_managers({}, {}, {}) == []

    def test_greedy_picks_highest_jaccard_first(self) -> None:
        # city_A overlaps strongly with am_X (3/3), city_B with am_Y (3/3).
        city_sigs = {"A": {1, 2, 3}, "B": {4, 5, 6}}
        am_sigs = {"X": {1, 2, 3, 99}, "Y": {4, 5, 6}, "Z": {7, 8, 9}}
        am_counts = {"X": 100, "Y": 80, "Z": 50}  # Z excluded (top-N=2)
        result = match_cities_to_area_managers(city_sigs, am_sigs, am_counts)
        by_city = {m.city_name: m for m in result}
        assert by_city["A"].area_manager == "X"
        assert by_city["B"].area_manager == "Y"

    def test_bijective_no_reuse_of_am(self) -> None:
        """貪欲でも city2 の 1 位が city1 と衝突したら 2 位を取る．"""
        city_sigs = {"C1": {1, 2, 3}, "C2": {1, 2, 3}}  # 両 city とも同じ signature
        am_sigs = {"X": {1, 2, 3}, "Y": {1, 2}}
        am_counts = {"X": 100, "Y": 80}
        result = match_cities_to_area_managers(city_sigs, am_sigs, am_counts)
        assert {m.area_manager for m in result} == {"X", "Y"}
        assert {m.city_name for m in result} == {"C1", "C2"}

    def test_confidence_high_medium_low(self) -> None:
        assert _confidence_label(0.3) == "high"
        assert _confidence_label(0.25) == "high"
        assert _confidence_label(0.2) == "medium"
        assert _confidence_label(0.15) == "medium"
        assert _confidence_label(0.1) == "low"

    def test_top_n_filter_limits_candidate_ams(self) -> None:
        """len(cities)=1 なら residence 数トップ 1 件の AM のみ候補．"""
        city_sigs = {"A": {1, 2, 3}}
        # Y has perfect overlap but fewer residences → excluded (top-1 = X)
        am_sigs = {"X": {1}, "Y": {1, 2, 3}}
        am_counts = {"X": 500, "Y": 5}
        result = match_cities_to_area_managers(city_sigs, am_sigs, am_counts)
        assert len(result) == 1
        assert result[0].area_manager == "X"


class TestBuildAmConsumptionSignatures:
    def test_collects_product_guids_per_am(self) -> None:
        from anno_save_analyzer.trade.population import ProductSaturation

        a = ResidenceAggregate(
            area_manager="AM_1",
            product_saturations=(
                ProductSaturation(product_guid=1, current=0.5, average=0.5),
                ProductSaturation(product_guid=2, current=0.5, average=0.5),
            ),
        )
        b = ResidenceAggregate(
            area_manager="AM_2",
            product_saturations=(ProductSaturation(product_guid=2, current=0.7, average=0.7),),
        )
        out = build_am_consumption_signatures([a, b])
        assert out == {"AM_1": {1, 2}, "AM_2": {2}}


class TestCityAreaMatch:
    def test_fields(self) -> None:
        m = CityAreaMatch(
            city_name="Osaka",
            area_manager="AreaManager_8771",
            jaccard=0.42,
            confidence="high",
        )
        assert m.city_name == "Osaka"
        assert m.area_manager == "AreaManager_8771"
        assert m.jaccard == 0.42


# ---------------- Tier breakdown ----------------


def _build_am_with_object_residences(
    am_tag_name: str = "AreaManager_8771",
    residences: list[dict] | None = None,
) -> bytes:
    """``AreaManager > GameObject > objects > <1>`` 階層を挟んで Residence7 を配置．

    各 residence dict は ``_build_am_with_residences`` と同仕様に加えて
    ``guid`` キーを持つ．object entry 直下の ``guid`` attrib として書き出し，
    ``BuildingDictionary`` の tier ルックアップ対象になる．
    """
    residences = residences or []
    tags = {
        2: am_tag_name,
        3: "GameObject",
        4: "objects",
        5: "Residence7",
        6: "ConsumptionStates",
    }
    attribs = {
        0x8001: "ResidentCount",
        0x8002: "ProductMoneyOutput",
        0x8003: "NewspaperMoneyOutput",
        0x8004: "AverageNeedSaturation",
        0x8005: "CurrentSaturation",
        0x8006: "AverageSaturation",
        0x8007: "guid",
    }
    events: list[Event] = [("T", 2), ("T", 3), ("T", 4)]  # AreaManager > GameObject > objects
    for r in residences:
        events.append(("T", 1))  # <1> object entry
        if r.get("guid") is not None:
            events.append(("A", 0x8007, _i32_bytes(r["guid"])))
        events.append(("T", 5))  # Residence7
        events.append(("A", 0x8001, _i32_bytes(r.get("resident_count", 0))))
        events.append(("A", 0x8004, _f32_bytes(r.get("avg_saturation", 0.0))))
        events.append(("X",))  # close Residence7
        events.append(("X",))  # close <1>
    events.append(("X",))  # close objects
    events.append(("X",))  # close GameObject
    events.append(("X",))  # close AreaManager
    return minimal_v3(tags=tags, attribs=attribs, events=events)


def _dict(entries: dict[int, BuildingEntry]) -> BuildingDictionary:
    return BuildingDictionary(entries=entries)


class TestTierBreakdown:
    def test_no_buildings_yields_empty_tier_breakdown(self) -> None:
        """buildings 未指定 (既存呼び出し互換) なら tier_breakdown は空．"""
        buf = _build_am_with_object_residences(
            residences=[{"guid": 1010343, "resident_count": 10, "avg_saturation": 0.5}]
        )
        out = list_residence_aggregates(buf)
        assert len(out) == 1
        assert out[0].tier_breakdown == ()
        assert out[0].resident_total == 10

    def test_single_tier_all_residences(self) -> None:
        """全住居が同じ tier．tier_breakdown に 1 件 summary が出る．"""
        buildings = _dict(
            {
                1010343: BuildingEntry(
                    guid=1010343,
                    name="Farmer Residence",
                    kind="residence",
                    template="ResidenceBuilding",
                    tier="farmer",
                )
            }
        )
        buf = _build_am_with_object_residences(
            residences=[
                {"guid": 1010343, "resident_count": 10, "avg_saturation": 0.5},
                {"guid": 1010343, "resident_count": 20, "avg_saturation": 0.8},
            ]
        )
        out = list_residence_aggregates(buf, buildings=buildings)
        agg = out[0]
        assert agg.resident_total == 30
        assert len(agg.tier_breakdown) == 1
        ts = agg.tier_breakdown[0]
        assert ts.tier == "farmer"
        assert ts.residence_count == 2
        assert ts.resident_total == 30
        # residents weighted mean: (10*0.5 + 20*0.8) / 30 = 0.7
        assert ts.avg_saturation_mean == pytest.approx(0.7)

    def test_mixed_tiers_separated(self) -> None:
        """複数 tier が混在する場合にそれぞれ集計される．"""
        buildings = _dict(
            {
                1010343: BuildingEntry(
                    guid=1010343,
                    name="Farmer",
                    kind="residence",
                    template="ResidenceBuilding",
                    tier="farmer",
                ),
                1010345: BuildingEntry(
                    guid=1010345,
                    name="Worker",
                    kind="residence",
                    template="ResidenceBuilding",
                    tier="worker",
                ),
            }
        )
        buf = _build_am_with_object_residences(
            residences=[
                {"guid": 1010343, "resident_count": 10, "avg_saturation": 0.9},
                {"guid": 1010345, "resident_count": 50, "avg_saturation": 0.6},
                {"guid": 1010345, "resident_count": 30, "avg_saturation": 0.4},
            ]
        )
        out = list_residence_aggregates(buf, buildings=buildings)
        breakdown = {ts.tier: ts for ts in out[0].tier_breakdown}
        assert set(breakdown) == {"farmer", "worker"}
        assert breakdown["farmer"].residence_count == 1
        assert breakdown["farmer"].resident_total == 10
        assert breakdown["worker"].residence_count == 2
        assert breakdown["worker"].resident_total == 80
        # worker weighted mean: (50*0.6 + 30*0.4) / 80 = 0.525
        assert breakdown["worker"].avg_saturation_mean == pytest.approx(0.525)

    def test_unknown_tier_fallback_when_guid_missing_or_no_tier(self) -> None:
        """buildings に登録されてない / tier=None な住居は ``unknown`` に集約．"""
        buildings = _dict(
            {
                # tier 無し
                1010343: BuildingEntry(
                    guid=1010343,
                    name="Colony",
                    kind="residence",
                    template="ResidenceBuilding7_Colony",
                    tier=None,
                ),
            }
        )
        buf = _build_am_with_object_residences(
            residences=[
                {"guid": 1010343, "resident_count": 10, "avg_saturation": 0.5},
                # buildings に未登録な guid
                {"guid": 9999999, "resident_count": 5, "avg_saturation": 0.3},
            ]
        )
        out = list_residence_aggregates(buf, buildings=buildings)
        breakdown = {ts.tier: ts for ts in out[0].tier_breakdown}
        assert breakdown == {"unknown": breakdown["unknown"]}
        # 両住居まとめて unknown に合流
        assert breakdown["unknown"].residence_count == 2
        assert breakdown["unknown"].resident_total == 15
