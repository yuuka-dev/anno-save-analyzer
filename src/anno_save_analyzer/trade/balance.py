"""Supply balance engine (v0.4 #12)．

島単位で「生産 / 消費 / delta」の per-product バランスを算出する．

## 依存

- ``FactoryAggregate`` (trade.factories) — 供給側 (factory instance 群)
- ``FactoryRecipeTable`` (trade.factory_recipes) — Calculator 由来の tpmin /
  outputs マップ
- ``ResidenceAggregate.tier_breakdown`` (trade.population) — tier 別の人口
- ``ConsumptionTable`` (trade.consumption) — tier × product の tpmin/人

## 計算式

- **生産量 (ton/min)** = Σ over factory instances of
  ``productivity × recipe.tpmin × output.amount``
- **消費量 (ton/min)** = Σ over tier × needs of
  ``tier.resident_total × need.tpmin``
  - ``is_bonus_need`` の物資は通常消費に含めない
  - **unlock 未達の物資は除外**．Calculator の ``tier.needs`` は tier の
    潜在的な全 need 候補．書記長の島で実際 unlock されてるかは
    ``ResidenceAggregate.product_saturations`` (save の ``ConsumptionStates``
    観測値) で判定し，観測されてない need は加算しない (「ビスケット
    要求されてないのに消費加算される」問題の修正)．observe ゼロの島は
    tier.needs を素直に使う (都市再建直後など tier breakdown だけで推定
    したいフォールバック)．
- **delta** = produced - consumed

複数島の集計は ``SupplyBalanceTable.aggregate`` で area_manager 集合を指定
して行う．
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, Field, computed_field

from .consumption import ConsumptionTable, PopulationTier
from .factories import FactoryAggregate
from .factory_recipes import FactoryRecipeTable
from .population import ResidenceAggregate

# tier breakdown の key (``residence_tier0N`` から推定した小文字名) から
# ConsumptionTable 側の英語 ``name`` への map．
_TIER_KEY_TO_CONSUMPTION_NAME: dict[str, str] = {
    "farmer": "Farmers",
    "worker": "Workers",
    "artisan": "Artisans",
    "engineer": "Engineers",
    "investor": "Investors",
    "jornaleros": "Jornaleros",
    "obreros": "Obreros",
    "shepherd": "Shepherds",
    "elder": "Elders",
    "explorer": "Explorers",
    "technician": "Technicians",
    "scholar": "Scholars",
    "artista": "Artista",
}


class ProductBalance(BaseModel):
    """1 物資あたりの生産 / 消費 / delta (ton/min 単位)．"""

    product_guid: int
    produced_per_minute: float = 0.0
    consumed_per_minute: float = 0.0

    model_config = {"frozen": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def delta_per_minute(self) -> float:
        """正なら黒字 (余剰)，負なら赤字 (不足)．"""
        return self.produced_per_minute - self.consumed_per_minute

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_deficit(self) -> bool:
        """消費が生産を上回る (赤字) かどうか．許容誤差 1e-9．"""
        return self.produced_per_minute + 1e-9 < self.consumed_per_minute


class IslandBalance(BaseModel):
    """1 島分の supply balance．``products`` は物資 GUID 昇順．"""

    area_manager: str
    city_name: str | None = None
    resident_total: int = 0
    """寄与した人口．aggregate 時には合計人口．"""
    products: tuple[ProductBalance, ...] = Field(default_factory=tuple)

    model_config = {"frozen": True}

    def deficits(self) -> tuple[ProductBalance, ...]:
        """赤字品目だけ返す (最大赤字→小の順)．"""
        return tuple(
            sorted(
                (p for p in self.products if p.is_deficit),
                key=lambda p: p.delta_per_minute,
            )
        )


class SupplyBalanceTable(BaseModel):
    """島ごとの IslandBalance 群．複数島集計は ``aggregate``/``combined``．"""

    islands: tuple[IslandBalance, ...] = Field(default_factory=tuple)

    model_config = {"frozen": True}

    def by_area_manager(self) -> dict[str, IslandBalance]:
        return {isl.area_manager: isl for isl in self.islands}

    def aggregate(self, area_managers: Iterable[str] | None = None) -> IslandBalance:
        """指定した area_manager 集合 (``None`` なら全島) を合算した総計を返す．

        集計 IslandBalance の ``area_manager`` は ``"<aggregate>"`` で固定．
        ``city_name`` は選択島が 1 件のみならその島名，複数なら結合キー．
        """
        if area_managers is None:
            selected = self.islands
        else:
            wanted = set(area_managers)
            selected = tuple(isl for isl in self.islands if isl.area_manager in wanted)
        produced: dict[int, float] = {}
        consumed: dict[int, float] = {}
        residents = 0
        for isl in selected:
            residents += isl.resident_total
            for p in isl.products:
                produced[p.product_guid] = produced.get(p.product_guid, 0.0) + p.produced_per_minute
                consumed[p.product_guid] = consumed.get(p.product_guid, 0.0) + p.consumed_per_minute
        products = tuple(
            ProductBalance(
                product_guid=g,
                produced_per_minute=produced.get(g, 0.0),
                consumed_per_minute=consumed.get(g, 0.0),
            )
            for g in sorted(set(produced) | set(consumed))
        )
        city_name: str | None = None
        if len(selected) == 1:
            city_name = selected[0].city_name
        elif selected:
            names = [s.city_name for s in selected if s.city_name]
            city_name = " + ".join(names) if names else None
        return IslandBalance(
            area_manager="<aggregate>",
            city_name=city_name,
            resident_total=residents,
            products=products,
        )


def build_balance_table(
    *,
    residences: Iterable[ResidenceAggregate],
    factories: Iterable[FactoryAggregate] = (),
    recipes: FactoryRecipeTable | None = None,
    consumption: ConsumptionTable | None = None,
    city_names: dict[str, str] | None = None,
    include_bonus_needs: bool = False,
) -> SupplyBalanceTable:
    """供給側 (factories + recipes) と消費側 (residences + consumption) から
    ``SupplyBalanceTable`` を組み立てる．

    - ``recipes`` 未指定なら生産量は全 0
    - ``consumption`` 未指定なら消費量は全 0
    - ``include_bonus_needs=False`` の時 Rum / Spirits 等の嗜好品需要は無視 (Calculator の
      ``isBonusNeed`` フラグに従う)．住民 upgrade には必要だが通常供給計算には含めない
    """
    factories_by_am: dict[str, FactoryAggregate] = {f.area_manager: f for f in factories}
    islands: list[IslandBalance] = []
    for res in residences:
        produced = _produced_for_island(factories_by_am.get(res.area_manager), recipes)
        consumed = _consumed_for_island(res, consumption, include_bonus_needs=include_bonus_needs)
        guids = sorted(set(produced) | set(consumed))
        products = tuple(
            ProductBalance(
                product_guid=g,
                produced_per_minute=produced.get(g, 0.0),
                consumed_per_minute=consumed.get(g, 0.0),
            )
            for g in guids
        )
        islands.append(
            IslandBalance(
                area_manager=res.area_manager,
                city_name=(city_names or {}).get(res.area_manager),
                resident_total=res.resident_total,
                products=products,
            )
        )
    return SupplyBalanceTable(islands=tuple(islands))


def _produced_for_island(
    factories: FactoryAggregate | None,
    recipes: FactoryRecipeTable | None,
) -> dict[int, float]:
    if factories is None or recipes is None:
        return {}
    totals: dict[int, float] = {}
    for inst in factories.instances:
        recipe = recipes.get(inst.building_guid)
        if recipe is None:
            continue
        for guid, rate in recipe.produced_per_minute(inst.productivity).items():
            totals[guid] = totals.get(guid, 0.0) + rate
    return totals


def _consumed_for_island(
    residence: ResidenceAggregate,
    consumption: ConsumptionTable | None,
    *,
    include_bonus_needs: bool,
) -> dict[int, float]:
    if consumption is None or not residence.tier_breakdown:
        return {}
    # 観測済 need で filter．``product_saturations`` に登録されている物資が
    # save の ``ConsumptionStates`` で実際消費記録のある need = unlock 済．
    # None (観測ゼロ) の場合は tier.needs を素直に加算 (既存互換の fallback)．
    observed: set[int] | None = None
    if residence.product_saturations:
        observed = {ps.product_guid for ps in residence.product_saturations}

    totals: dict[int, float] = {}
    # 事前に consumption の tier を英語名で index して繰り返し linear search を回避
    tier_by_name: dict[str, PopulationTier] = {t.name: t for t in consumption.tiers}
    for ts in residence.tier_breakdown:
        english_name = _TIER_KEY_TO_CONSUMPTION_NAME.get(ts.tier)
        if english_name is None:
            continue
        tier = tier_by_name.get(english_name)
        if tier is None:
            continue
        for need in tier.needs:
            if need.tpmin is None:
                continue
            if need.is_bonus_need and not include_bonus_needs:
                continue
            if observed is not None and need.product_guid not in observed:
                continue
            totals[need.product_guid] = (
                totals.get(need.product_guid, 0.0) + ts.resident_total * need.tpmin
            )
    return totals
