"""島ごとの人口 / 住居消費パーサ (v0.4.3 PR B).

内側 Session DOM の ``AreaManager_<N>`` 配下から住居・人口・消費データを抽出する．

## DOM 構造 (実測 2026-04-22)

```
GameSessionManager
├─ AreaInfo > <1>                     (CityName 持ち = プレイヤー島)
│   └─ AreaEconomy > StorageTrends   (trade / storage — 既存)
└─ AreaManagers
    └─ AreaManager_<N>                (島実体．N = 内部 area ID)
        ├─ AreaPopulationManager
        ├─ AreaResidenceConsumptionManager
        ├─ AreaWideNeedsManager
        └─ AreaObjectManager > GameObject > objects > <1>
            ├─ A guid, ID, Position, ...
            └─ Residence7                (1 建物)
                ├─ A ResidentCount                       i32
                ├─ A ProductMoneyOutput                  i32
                ├─ A NewspaperMoneyOutput                i32
                ├─ A AverageNeedSaturation               float32 (i32 bit pattern)
                ├─ A AverageNeedSaturationExcludingBonusNeeds
                └─ ConsumptionStates
                    ├─ A <anon> ProductGUID  i32
                    └─ <1>
                        ├─ A CurrentSaturation      float32
                        └─ A AverageSaturation      float32
```

## 島名への結合 (heuristic)

AreaInfo と AreaManager は同じ save で並列に存在するが構造的な join キー無し．
対策として **Jaccard overlap heuristic** を採用:

1. プレイヤー島 = ``CityName`` を持つ AreaInfo entry
2. 各 CityName について StorageTrends の nonzero 品目集合を signature に
3. 各 AreaManager_N について Residence7 ConsumptionStates の品目集合を signature に
4. Jaccard 降順で greedy な bijective assignment

実測 (2026-04-22, 18 プレイヤー島) で最大都市は全セッション書記長確認通りで
正解．低 tier 都市は Jaccard が低くなるため「低信頼」扱いとし，``confidence``
フィールドで表面化する．ユーザは信頼度で filter / 手動 override できる．
"""

from __future__ import annotations

import struct
from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import BaseModel, Field, computed_field

from anno_save_analyzer.parser.filedb import (
    EventKind,
    TagSection,
    detect_version,
    iter_dom,
    parse_tag_section,
)

from .buildings import BuildingDictionary

_AREA_MANAGER_PREFIX = "AreaManager_"
_OBJECTS = "objects"
_RESIDENCE7 = "Residence7"
_CONSUMPTION_STATES = "ConsumptionStates"
_RESIDENT_COUNT = "ResidentCount"
_PRODUCT_MONEY = "ProductMoneyOutput"
_NEWSPAPER_MONEY = "NewspaperMoneyOutput"
_AVG_SATURATION = "AverageNeedSaturation"
_AVG_SATURATION_EX_BONUS = "AverageNeedSaturationExcludingBonusNeeds"
_CURRENT_SAT = "CurrentSaturation"
_AVG_SAT = "AverageSaturation"
_GUID_ATTRIB = "guid"
_UNKNOWN_TIER = "unknown"
"""``BuildingDictionary`` で tier が未判定の Residence を集計するキー．Arctic
/ Colony 系など assets.xml の internal name が ``residence_tier0N`` 命名規則
から外れてるケースが該当する．"""


def _i32(buf: bytes) -> int:
    return struct.unpack_from("<i", buf, 0)[0] if len(buf) >= 4 else 0


def _f32(buf: bytes) -> float:
    return struct.unpack_from("<f", buf, 0)[0] if len(buf) >= 4 else 0.0


class ProductSaturation(BaseModel):
    """住居消費で 1 物資あたりの充足率．``CurrentSaturation`` は 0.0–1.0 の float．"""

    product_guid: int
    current: float
    """直近の満足率．0=不足で不満，1=完全充足．"""
    average: float
    """直近平均．short-term ノイズが乗った current よりトレンドを見るのに使う．"""

    model_config = {"frozen": True}


class TierSummary(BaseModel):
    """1 住居階層 (Farmer / Worker / ...) 分の集計．島別 tier breakdown の要素．"""

    tier: str
    """``farmer`` / ``worker`` / ``artisan`` / ``engineer`` / ``investor`` /
    ``jornaleros`` / ``obreros`` / ``unknown``．``unknown`` は
    ``BuildingDictionary`` で tier 判定できなかった Residence (Arctic / Colony
    系など命名規則外)．"""
    residence_count: int = 0
    resident_total: int = 0
    avg_saturation_mean: float = 0.0
    """住居平均 ``AverageNeedSaturation`` (residents weighted)．"""

    model_config = {"frozen": True}


class ResidenceAggregate(BaseModel):
    """1 島分の住居サマリ．住居 (Residence7) 群の集計値．"""

    area_manager: str = Field(..., description="AreaManager_<N> タグ名")
    residence_count: int = 0
    resident_total: int = 0
    """``ResidentCount`` の合計 = 島の全人口．"""
    product_money_total: int = 0
    newspaper_money_total: int = 0
    avg_saturation_mean: float = 0.0
    """住居平均 ``AverageNeedSaturation`` (residents weighted)．"""
    product_saturations: tuple[ProductSaturation, ...] = Field(default_factory=tuple)
    """島全体で観測された物資 × (current, average)．全住居の平均を取る．"""
    tier_breakdown: tuple[TierSummary, ...] = Field(default_factory=tuple)
    """Farmer / Worker / ... 別の内訳．``list_residence_aggregates`` に
    ``buildings`` を渡した時のみ populate．渡さない場合は空 tuple．"""

    model_config = {"frozen": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def residents_per_residence(self) -> float:
        if self.residence_count == 0:
            return 0.0
        return self.resident_total / self.residence_count

    @computed_field  # type: ignore[prop-decorator]
    @property
    def gold_per_resident(self) -> float:
        if self.resident_total == 0:
            return 0.0
        return (self.product_money_total + self.newspaper_money_total) / self.resident_total


def list_residence_aggregates(
    inner_session: bytes,
    *,
    buildings: BuildingDictionary | None = None,
) -> tuple[ResidenceAggregate, ...]:
    """内側 Session FileDB から AreaManager 単位の住居サマリを抽出．

    プレイヤー島だけじゃなく Residence7 を持つ全 AreaManager を返す (NPC 都市
    含む)．プレイヤー絞り込みは上位 layer の city name 結合で行う．

    ``buildings`` を渡すと親 ``objects > <1>`` の ``guid`` attrib から
    ``BuildingEntry.tier`` を引き，``tier_breakdown`` に tier 別集計を populate
    する．未指定なら ``tier_breakdown`` は空 tuple になり既存挙動と一致．
    """
    if not inner_session:
        return ()
    version = detect_version(inner_session)
    section = parse_tag_section(inner_session, version)
    accums = _walk_residences(inner_session, version, section, buildings)
    return tuple(_freeze(acc) for acc in accums.values() if acc.residence_count > 0)


def _walk_residences(
    inner: bytes,
    version,
    section: TagSection,
    buildings: BuildingDictionary | None,
) -> dict[str, _ResidenceAccumMutable]:
    id2name = dict(section.tags.entries)
    r7_id = next((i for i, n in id2name.items() if n == _RESIDENCE7), None)
    cs_id = next((i for i, n in id2name.items() if n == _CONSUMPTION_STATES), None)
    if r7_id is None:
        return {}

    stack: list[str] = []
    accums: dict[str, _ResidenceAccumMutable] = {}
    in_am: tuple[int, str] | None = None
    in_obj_entry: int | None = None  # objects > <1> の depth
    obj_guid: int | None = None  # 現在の object entry の ``guid`` attrib
    in_r7: int | None = None
    current_residence: dict[str, bytes] = {}
    in_cs: int | None = None
    in_cs_entry: int | None = None
    current_cs_guid: int | None = None
    current_cs_pair: list[float] = [0.0, 0.0]  # [current, average]

    # `saw_saturation` は cs entry に CurrentSaturation/AverageSaturation が実際に
    # 現れたかを追跡．saturation 属性なしの GUID (登録だけで未観測) は signature
    # から除外して jaccard 精度を上げる．
    saw_saturation = False

    for ev in iter_dom(inner, version, tag_section=section):
        if ev.kind is EventKind.TAG:
            name = ev.name or f"<{ev.id_}>"
            stack.append(name)
            depth = len(stack)
            if name.startswith(_AREA_MANAGER_PREFIX) and in_am is None:
                in_am = (depth, name)
                accums.setdefault(name, _ResidenceAccumMutable(area_manager=name))
            elif (
                in_am is not None
                and in_obj_entry is None
                and name == "<1>"
                and len(stack) >= 2
                and stack[-2] == _OBJECTS
            ):
                in_obj_entry = depth
                obj_guid = None
            elif in_am is not None and ev.id_ == r7_id and in_r7 is None:
                in_r7 = depth
                current_residence = {}
            elif in_r7 is not None and cs_id is not None and ev.id_ == cs_id and in_cs is None:
                in_cs = depth
            elif in_cs is not None and in_cs_entry is None and name == "<1>" and depth == in_cs + 1:
                in_cs_entry = depth
                current_cs_pair[:] = [0.0, 0.0]
                saw_saturation = False
            continue

        if ev.kind is EventKind.ATTRIB:
            if (
                in_obj_entry is not None
                and in_r7 is None
                and len(stack) == in_obj_entry
                and ev.name == _GUID_ATTRIB
            ):
                obj_guid = _i32(ev.content)
            elif in_r7 is not None and len(stack) == in_r7:
                current_residence[ev.name or ""] = ev.content
            elif (
                in_cs is not None
                and len(stack) == in_cs
                and ev.name is None
                and len(ev.content) == 4
            ):
                current_cs_guid = _i32(ev.content)
            elif in_cs_entry is not None and len(stack) == in_cs_entry:
                if ev.name == _CURRENT_SAT:
                    current_cs_pair[0] = _f32(ev.content)
                    saw_saturation = True
                elif ev.name == _AVG_SAT:
                    current_cs_pair[1] = _f32(ev.content)
                    saw_saturation = True
            continue

        # Terminator
        if not stack:
            continue
        closing_depth = len(stack)
        if in_cs_entry is not None and closing_depth == in_cs_entry:
            # 1 product entry close: accumulate if we have guid AND saturation attrib
            # was actually observed (空 entry = その住居階層はその物資を消費してない)
            if current_cs_guid is not None and in_am is not None and saw_saturation:
                acc = accums[in_am[1]]
                totals = acc.product_saturation_totals.setdefault(current_cs_guid, [0.0, 0.0, 0])
                totals[0] += current_cs_pair[0]
                totals[1] += current_cs_pair[1]
                totals[2] += 1
            in_cs_entry = None
        if in_cs is not None and closing_depth == in_cs:
            in_cs = None
            current_cs_guid = None
        if in_r7 is not None and closing_depth == in_r7:
            # Residence7 close: commit aggregates
            if in_am is not None:
                residents = _i32(current_residence.get(_RESIDENT_COUNT, b""))
                prod_money = _i32(current_residence.get(_PRODUCT_MONEY, b""))
                newsp_money = _i32(current_residence.get(_NEWSPAPER_MONEY, b""))
                avg_sat = _f32(current_residence.get(_AVG_SATURATION, b""))
                acc = accums[in_am[1]]
                acc.residence_count += 1
                acc.resident_total += residents
                acc.product_money_total += prod_money
                acc.newspaper_money_total += newsp_money
                acc.saturation_weighted += avg_sat * residents
                # tier 分類．buildings が与えられている場合のみ意味がある．
                if buildings is not None:
                    tier_key = _resolve_tier(obj_guid, buildings)
                    bucket = acc.tier_totals.setdefault(tier_key, [0, 0, 0.0])
                    bucket[0] += 1  # residence_count
                    bucket[1] += residents
                    bucket[2] += avg_sat * residents
            in_r7 = None
            current_residence = {}
        if in_obj_entry is not None and closing_depth == in_obj_entry:
            in_obj_entry = None
            obj_guid = None
        if in_am is not None and closing_depth == in_am[0]:
            in_am = None
        stack.pop()

    return accums


def _resolve_tier(guid: int | None, buildings: BuildingDictionary) -> str:
    """``BuildingDictionary`` で building_guid → tier 文字列を引く．判定不能は
    ``"unknown"`` を返す．"""
    if guid is None:
        return _UNKNOWN_TIER
    entry = buildings.get(guid)
    if entry is None or entry.tier is None:
        return _UNKNOWN_TIER
    return entry.tier


class _ResidenceAccumMutable:
    __slots__ = (
        "area_manager",
        "residence_count",
        "resident_total",
        "product_money_total",
        "newspaper_money_total",
        "saturation_weighted",
        "product_saturation_totals",
        "tier_totals",
    )

    def __init__(self, area_manager: str) -> None:
        self.area_manager = area_manager
        self.residence_count = 0
        self.resident_total = 0
        self.product_money_total = 0
        self.newspaper_money_total = 0
        self.saturation_weighted = 0.0
        self.product_saturation_totals: dict[int, list[float]] = {}
        # key: tier name (``"farmer"`` / ``"unknown"`` 等)，
        # value: [residence_count, resident_total, saturation_weighted]
        self.tier_totals: dict[str, list] = {}


def _freeze(acc: _ResidenceAccumMutable) -> ResidenceAggregate:
    sats: list[ProductSaturation] = []
    for guid, (sum_cur, sum_avg, n) in sorted(acc.product_saturation_totals.items()):
        if n == 0:
            continue
        sats.append(ProductSaturation(product_guid=guid, current=sum_cur / n, average=sum_avg / n))
    mean_sat = acc.saturation_weighted / acc.resident_total if acc.resident_total else 0.0
    tier_breakdown: list[TierSummary] = []
    for tier_key in sorted(acc.tier_totals.keys()):
        count, residents, sat_weighted = acc.tier_totals[tier_key]
        tier_mean = sat_weighted / residents if residents else 0.0
        tier_breakdown.append(
            TierSummary(
                tier=tier_key,
                residence_count=count,
                resident_total=residents,
                avg_saturation_mean=tier_mean,
            )
        )
    return ResidenceAggregate(
        area_manager=acc.area_manager,
        residence_count=acc.residence_count,
        resident_total=acc.resident_total,
        product_money_total=acc.product_money_total,
        newspaper_money_total=acc.newspaper_money_total,
        avg_saturation_mean=mean_sat,
        product_saturations=tuple(sats),
        tier_breakdown=tuple(tier_breakdown),
    )


# ----------------- AreaManager → CityName resolver ---------------


@dataclass(frozen=True)
class CityAreaMatch:
    """1 組の (CityName, AreaManager) 結合結果．``confidence`` で信頼度を表す．"""

    city_name: str
    area_manager: str
    jaccard: float
    """物資集合の Jaccard 類似度．高いほど信頼できる．"""
    confidence: str
    """``high`` (>= 0.25) / ``medium`` (>= 0.15) / ``low`` (それ以下)．"""


def match_cities_to_area_managers(
    city_signatures: dict[str, set[int]],
    am_signatures: dict[str, set[int]],
    am_residence_counts: dict[str, int],
) -> list[CityAreaMatch]:
    """CityName ↔ AreaManager の bijective match (greedy jaccard)．

    入力:
    - ``city_signatures``: city_name → StorageTrends nonzero product GUIDs
    - ``am_signatures``: area_manager → Residence7 consumption product GUIDs
    - ``am_residence_counts``: area_manager → residence 総数 (filter 用)

    処理:
    1. AM を residence 数 top-N (N = len(cities)) に絞る (プレイヤー島だけ残す)
    2. すべての (city, am) ペアの Jaccard を計算
    3. Jaccard 降順で greedy に割当 (重複無し)

    実測で最大都市は全件正解．低 tier 都市は Jaccard 0.1-0.2 で「tentative」
    扱いとなるが，それでも positional fallback より accurate．
    """
    n = len(city_signatures)
    if n == 0:
        return []
    # top-N by residences = candidate player AMs
    sorted_ams = sorted(am_residence_counts.items(), key=lambda x: -x[1])[:n]
    candidate_ams = {am: am_signatures.get(am, set()) for am, _ in sorted_ams}

    pairs: list[tuple[str, str, float]] = []
    for city, cprods in city_signatures.items():
        for am, aprods in candidate_ams.items():
            inter = len(cprods & aprods)
            union = len(cprods | aprods)
            jaccard = inter / union if union else 0.0
            pairs.append((city, am, jaccard))
    pairs.sort(key=lambda p: -p[2])

    assigned_cities: set[str] = set()
    assigned_ams: set[str] = set()
    matches: list[CityAreaMatch] = []
    for city, am, j in pairs:
        if city in assigned_cities or am in assigned_ams:
            continue
        assigned_cities.add(city)
        assigned_ams.add(am)
        matches.append(
            CityAreaMatch(
                city_name=city,
                area_manager=am,
                jaccard=round(j, 3),
                confidence=_confidence_label(j),
            )
        )
    return matches


def _confidence_label(jaccard: float) -> str:
    if jaccard >= 0.25:
        return "high"
    if jaccard >= 0.15:
        return "medium"
    return "low"


def build_am_consumption_signatures(
    aggregates: Iterable[ResidenceAggregate],
) -> dict[str, set[int]]:
    """``ResidenceAggregate`` 群から AM 単位の product GUID signature を作る．"""
    out: dict[str, set[int]] = {}
    for agg in aggregates:
        out[agg.area_manager] = {p.product_guid for p in agg.product_saturations}
    return out
