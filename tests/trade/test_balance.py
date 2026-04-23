"""``trade.balance`` engine の単体テスト．

合成 FactoryAggregate / ResidenceAggregate + tiny ConsumptionTable /
FactoryRecipeTable を使って生産 / 消費 / delta が正しく出ることを検証する．
"""

from __future__ import annotations

import pytest

from anno_save_analyzer.trade.balance import (
    SupplyBalanceTable,
    build_balance_table,
)
from anno_save_analyzer.trade.consumption import (
    ConsumptionTable,
    PopulationTier,
    TierNeed,
)
from anno_save_analyzer.trade.factories import FactoryAggregate, FactoryInstance
from anno_save_analyzer.trade.factory_recipes import (
    FactoryRecipe,
    FactoryRecipeTable,
    RecipeOutput,
)
from anno_save_analyzer.trade.population import (
    ProductSaturation,
    ResidenceAggregate,
    TierSummary,
)

# ---------- fixtures ----------


def _mk_residence(
    am: str = "AreaManager_1",
    residents: int = 0,
    tier_breakdown: tuple[TierSummary, ...] = (),
    observed_products: tuple[int, ...] = (),
) -> ResidenceAggregate:
    return ResidenceAggregate(
        area_manager=am,
        residence_count=sum(ts.residence_count for ts in tier_breakdown),
        resident_total=residents,
        tier_breakdown=tier_breakdown,
        product_saturations=tuple(
            ProductSaturation(product_guid=g, current=0.9, average=0.9) for g in observed_products
        ),
    )


def _mk_factory(
    am: str = "AreaManager_1",
    instances: tuple[FactoryInstance, ...] = (),
) -> FactoryAggregate:
    return FactoryAggregate(area_manager=am, instances=instances)


def _mk_consumption(*tiers: PopulationTier) -> ConsumptionTable:
    return ConsumptionTable(tiers=tuple(tiers))


def _mk_recipes(*recipes: FactoryRecipe) -> FactoryRecipeTable:
    return FactoryRecipeTable(recipes={r.guid: r for r in recipes})


# ---------- 生産のみ ----------


def test_production_only_no_residence_but_factories_yield_produce() -> None:
    """Residence が 1 件あり tier_breakdown=()．factory の生産だけ出る．"""
    recipes = _mk_recipes(
        FactoryRecipe(
            guid=100,
            name="Fishery",
            tpmin=2.0,
            outputs=(RecipeOutput(product_guid=200, amount=1.0),),
        )
    )
    residences = [_mk_residence(residents=10)]
    factories = [
        _mk_factory(
            instances=(
                FactoryInstance(building_guid=100, productivity=1.0),
                FactoryInstance(building_guid=100, productivity=0.5),
            )
        )
    ]
    table = build_balance_table(residences=residences, factories=factories, recipes=recipes)
    assert len(table.islands) == 1
    products = table.islands[0].products
    assert len(products) == 1
    p = products[0]
    assert p.product_guid == 200
    # 1.0 × 2.0 × 1.0 + 0.5 × 2.0 × 1.0 = 3.0 /min
    assert p.produced_per_minute == pytest.approx(3.0)
    assert p.consumed_per_minute == 0.0
    assert p.delta_per_minute == pytest.approx(3.0)
    assert not p.is_deficit


# ---------- 消費のみ ----------


def test_consumption_only_from_tier_breakdown() -> None:
    """Farmer tier に 100 residents．Fish (tpmin=0.0025) を 100 × 0.0025 = 0.25/min 消費．"""
    consumption = _mk_consumption(
        PopulationTier(
            guid=15000000,
            name="Farmers",
            needs=(TierNeed(product_guid=200, tpmin=0.0025),),
        )
    )
    residences = [
        _mk_residence(
            residents=100,
            tier_breakdown=(TierSummary(tier="farmer", residence_count=10, resident_total=100),),
        )
    ]
    table = build_balance_table(residences=residences, consumption=consumption)
    p = table.islands[0].products[0]
    assert p.product_guid == 200
    assert p.produced_per_minute == 0.0
    assert p.consumed_per_minute == pytest.approx(0.25)
    assert p.is_deficit


def test_bonus_needs_excluded_by_default() -> None:
    """isBonusNeed 物資は default で消費に含めない．"""
    consumption = _mk_consumption(
        PopulationTier(
            guid=15000000,
            name="Farmers",
            needs=(
                TierNeed(product_guid=200, tpmin=0.01),  # 通常
                TierNeed(product_guid=300, tpmin=0.02, is_bonus_need=True),  # bonus
            ),
        )
    )
    residences = [
        _mk_residence(
            residents=100,
            tier_breakdown=(TierSummary(tier="farmer", residence_count=10, resident_total=100),),
        )
    ]
    table = build_balance_table(residences=residences, consumption=consumption)
    guids = {p.product_guid for p in table.islands[0].products}
    assert 200 in guids
    assert 300 not in guids


def test_bonus_needs_included_when_flag_set() -> None:
    consumption = _mk_consumption(
        PopulationTier(
            guid=15000000,
            name="Farmers",
            needs=(TierNeed(product_guid=300, tpmin=0.02, is_bonus_need=True),),
        )
    )
    residences = [
        _mk_residence(
            residents=100,
            tier_breakdown=(TierSummary(tier="farmer", residence_count=10, resident_total=100),),
        )
    ]
    table = build_balance_table(
        residences=residences, consumption=consumption, include_bonus_needs=True
    )
    guids = {p.product_guid for p in table.islands[0].products}
    assert 300 in guids


def test_tier_not_in_map_is_skipped() -> None:
    """tier_breakdown の tier が ``_TIER_KEY_TO_CONSUMPTION_NAME`` に無ければ消費 0．"""
    consumption = _mk_consumption(
        PopulationTier(
            guid=15000000,
            name="Farmers",
            needs=(TierNeed(product_guid=200, tpmin=0.01),),
        )
    )
    residences = [
        _mk_residence(
            residents=100,
            tier_breakdown=(TierSummary(tier="unknown", residence_count=10, resident_total=100),),
        )
    ]
    table = build_balance_table(residences=residences, consumption=consumption)
    assert table.islands[0].products == ()


# ---------- observed need filter (unlock 未達の除外) ----------


def test_unlock_not_met_need_excluded_when_not_observed() -> None:
    """``product_saturations`` に無い need は unlock 未達と見なし加算しない．

    Calculator の Farmer tier には Fish と Biscuits 両方が候補として並ぶが
    書記長の save で Biscuits が要求されてない (ConsumptionStates に未登録)
    場合は消費に乗らない．
    """
    consumption = _mk_consumption(
        PopulationTier(
            guid=15000000,
            name="Farmers",
            needs=(
                TierNeed(product_guid=200, tpmin=0.01),  # Fish: 観測済
                TierNeed(product_guid=400, tpmin=0.02),  # Biscuits: 未観測 = unlock 外
            ),
        )
    )
    residences = [
        _mk_residence(
            residents=100,
            tier_breakdown=(TierSummary(tier="farmer", residence_count=10, resident_total=100),),
            observed_products=(200,),  # Fish のみ観測
        )
    ]
    table = build_balance_table(residences=residences, consumption=consumption)
    guids = {p.product_guid for p in table.islands[0].products}
    assert 200 in guids
    assert 400 not in guids


def test_no_observed_products_falls_back_to_all_needs() -> None:
    """``product_saturations`` 空なら tier.needs を全加算 (既存互換 fallback)．

    都市再建直後など save に tier_breakdown だけあって ConsumptionStates が
    populate されてないケースで 0 加算にならないようにする．
    """
    consumption = _mk_consumption(
        PopulationTier(
            guid=15000000,
            name="Farmers",
            needs=(
                TierNeed(product_guid=200, tpmin=0.01),
                TierNeed(product_guid=400, tpmin=0.02),
            ),
        )
    )
    residences = [
        _mk_residence(
            residents=100,
            tier_breakdown=(TierSummary(tier="farmer", residence_count=10, resident_total=100),),
            observed_products=(),  # 観測ゼロ
        )
    ]
    table = build_balance_table(residences=residences, consumption=consumption)
    guids = {p.product_guid for p in table.islands[0].products}
    # fallback: 両方の need が加算される
    assert guids == {200, 400}


# ---------- 混合 (生産 + 消費) ----------


def test_produced_minus_consumed_yields_delta() -> None:
    recipes = _mk_recipes(
        FactoryRecipe(
            guid=100,
            name="Fishery",
            tpmin=2.0,
            outputs=(RecipeOutput(product_guid=200, amount=1.0),),
        )
    )
    consumption = _mk_consumption(
        PopulationTier(
            guid=15000000,
            name="Farmers",
            needs=(TierNeed(product_guid=200, tpmin=0.02),),
        )
    )
    residences = [
        _mk_residence(
            am="AreaManager_1",
            residents=150,
            tier_breakdown=(TierSummary(tier="farmer", residence_count=15, resident_total=150),),
        )
    ]
    factories = [
        _mk_factory(
            am="AreaManager_1",
            instances=(FactoryInstance(building_guid=100, productivity=1.0),),
        )
    ]
    table = build_balance_table(
        residences=residences,
        factories=factories,
        recipes=recipes,
        consumption=consumption,
    )
    p = table.islands[0].products[0]
    # produced: 1 × 2.0 × 1.0 = 2.0 /min
    # consumed: 150 × 0.02 = 3.0 /min
    # delta: -1.0 (deficit)
    assert p.produced_per_minute == pytest.approx(2.0)
    assert p.consumed_per_minute == pytest.approx(3.0)
    assert p.delta_per_minute == pytest.approx(-1.0)
    assert p.is_deficit
    # deficits() returns sorted by worst first
    deficits = table.islands[0].deficits()
    assert deficits == (p,)


# ---------- 複数島 集計 ----------


def test_aggregate_sums_across_selected_islands() -> None:
    consumption = _mk_consumption(
        PopulationTier(
            guid=15000000,
            name="Farmers",
            needs=(TierNeed(product_guid=200, tpmin=0.01),),
        )
    )
    residences = [
        _mk_residence(
            am=f"AreaManager_{i}",
            residents=100,
            tier_breakdown=(TierSummary(tier="farmer", residence_count=10, resident_total=100),),
        )
        for i in (1, 2, 3)
    ]
    table = build_balance_table(residences=residences, consumption=consumption)
    # 全島合算
    combined = table.aggregate()
    assert combined.resident_total == 300
    assert combined.products[0].consumed_per_minute == pytest.approx(3.0)
    # 部分集合
    two = table.aggregate({"AreaManager_1", "AreaManager_2"})
    assert two.resident_total == 200
    assert two.products[0].consumed_per_minute == pytest.approx(2.0)
    # 単一島 → city_name が 1 島のものを継承
    single = table.aggregate({"AreaManager_3"})
    assert single.resident_total == 100


def test_aggregate_empty_selection_returns_empty() -> None:
    residences = [_mk_residence(am="AreaManager_1", residents=0, tier_breakdown=())]
    table = build_balance_table(residences=residences)
    out = table.aggregate({"AreaManager_NOT_EXIST"})
    assert out.resident_total == 0
    assert out.products == ()


def test_city_name_injected_from_map() -> None:
    residences = [_mk_residence(am="AreaManager_1", residents=10, tier_breakdown=())]
    table = build_balance_table(
        residences=residences,
        city_names={"AreaManager_1": "大都会岡山"},
    )
    assert table.islands[0].city_name == "大都会岡山"


def test_by_area_manager_lookup() -> None:
    residences = [_mk_residence(am=f"AreaManager_{i}") for i in (1, 2)]
    table = build_balance_table(residences=residences)
    lookup = table.by_area_manager()
    assert set(lookup) == {"AreaManager_1", "AreaManager_2"}


# ---------- edge ----------


def test_empty_inputs_yields_empty_table() -> None:
    table = build_balance_table(residences=())
    assert isinstance(table, SupplyBalanceTable)
    assert table.islands == ()
    assert table.aggregate().products == ()


def test_factories_on_island_without_recipe_do_not_crash() -> None:
    """recipe に未登録な factory は無視される (= 生産 0)．"""
    residences = [_mk_residence(am="A1", residents=10)]
    factories = [
        _mk_factory(am="A1", instances=(FactoryInstance(building_guid=9999, productivity=1.0),))
    ]
    recipes = _mk_recipes()  # 空 table
    table = build_balance_table(residences=residences, factories=factories, recipes=recipes)
    assert table.islands[0].products == ()
