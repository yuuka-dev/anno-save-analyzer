"""既存 StorageTrends / TradeEvent から派生する分析指標．

書記長要望 (v0.4.3) の「物資枯渇まで何分」「需要供給バランス」「不足物資一覧」を
純関数で計算する．人口 × 需要 の結合分析は v0.6 (別 PR) で追加予定．

依存:
- ``storage.IslandStorageTrend`` (1 島 × 1 物資の時系列)
- ``clock.SAMPLE_INTERVAL_TICKS`` (1 サンプル = 何 tick か)

slope は「サンプル単位 per unit-x」．``SAMPLE_INTERVAL_TICKS == TICKS_PER_MINUTE``
なら slope = 「分あたり変化量 (単位 物資/分)」になる．現状 1 sample = 1 minute
前提なので slope がそのまま「物資/分」の変化率として使える．
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable

from pydantic import BaseModel, Field, computed_field

from .models import Item
from .storage import IslandStorageTrend


class IslandProductRunway(BaseModel):
    """1 島 × 1 物資の「枯渇残り分数」．"""

    island_name: str
    product_guid: int
    latest: int
    """最新サンプル値．0 の物資は既に枯渇．"""
    slope_per_min: float
    """サンプル単位の線形回帰 slope．1 sample = 1 min なら「分あたり変化量」．
    正なら増加トレンド (生産 > 消費)，負なら減少 (消費 > 生産)．"""

    model_config = {"frozen": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def runway_min(self) -> float | None:
        """``slope_per_min`` が負のときに限り ``latest / |slope|`` を返す．

        増加 / 平坦は None (枯渇しない)．既に 0 の場合は 0.0 (即枯渇)．
        """
        if self.latest <= 0:
            return 0.0
        if self.slope_per_min >= 0:
            return None
        return float(self.latest) / -self.slope_per_min

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> str:
        """表示用ステータス label．"""
        if self.latest <= 0:
            return "depleted"
        if self.slope_per_min >= 0:
            return "stable_or_growing"
        r = self.runway_min
        if r is None:  # pragma: no cover - slope >= 0 の場合は上で拾う
            return "stable_or_growing"
        if r < 10:
            return "critical"
        if r < 60:
            return "warning"
        return "ok"


class ProductBalance(BaseModel):
    """1 物資の島横断な供給/需要バランス．"""

    product_guid: int
    surplus_islands: tuple[str, ...] = Field(default_factory=tuple)
    """slope > 0 の島（黒字＝生産過多）"""
    deficit_islands: tuple[str, ...] = Field(default_factory=tuple)
    """slope < 0 の島（赤字＝消費過多）"""
    net_slope_per_min: float = 0.0
    """全島の slope 合計．正なら全体余剰，負なら赤字．"""

    model_config = {"frozen": True}


def compute_runways(trends: Iterable[IslandStorageTrend]) -> list[IslandProductRunway]:
    """trend 群を runway 指標に変換．空 iterable に対しても安全に処理する．

    各 trend はそのまま ``IslandProductRunway`` に変換される。
    結果は ``runway_min`` 昇順 (逼迫順)．``None`` (安定/増加) は末尾にまとめる．
    """
    out: list[IslandProductRunway] = []
    for tr in trends:
        slope = tr.points.slope
        out.append(
            IslandProductRunway(
                island_name=tr.island_name,
                product_guid=tr.product_guid,
                latest=tr.latest,
                slope_per_min=slope,
            )
        )

    def _sort_key(r: IslandProductRunway) -> tuple[int, float]:
        # None は末尾にするため (has_runway, value) キー．
        if r.runway_min is None:
            return (1, math.inf)
        return (0, r.runway_min)

    out.sort(key=_sort_key)
    return out


def shortage_list(
    trends: Iterable[IslandStorageTrend],
    *,
    threshold_min: float | None = 60.0,
) -> list[IslandProductRunway]:
    """不足しとる (runway <= threshold) もの だけを抽出．

    既に枯渇 (``runway_min == 0``) は最優先で含める．``threshold_min=None``
    なら slope < 0 な全件を返す (枯渇予定全部)．
    """
    runways = compute_runways(trends)
    out: list[IslandProductRunway] = []
    for r in runways:
        if r.runway_min is None:
            continue  # 安定 / 増加は shortage じゃない
        if threshold_min is None or r.runway_min <= threshold_min:
            out.append(r)
    return out


def supply_demand_balance(
    trends: Iterable[IslandStorageTrend],
) -> list[ProductBalance]:
    """物資ごとに「黒字島 / 赤字島 / 合計 slope」を集計．

    結果は ``net_slope`` 降順 (余剰順)．ソートで全体状況が上から読める．
    """
    surplus: dict[int, list[str]] = defaultdict(list)
    deficit: dict[int, list[str]] = defaultdict(list)
    net: dict[int, float] = defaultdict(float)

    for tr in trends:
        slope = tr.points.slope
        net[tr.product_guid] += slope
        if slope > 0:
            surplus[tr.product_guid].append(tr.island_name)
        elif slope < 0:
            deficit[tr.product_guid].append(tr.island_name)

    all_guids = set(net.keys())
    out: list[ProductBalance] = []
    for guid in all_guids:
        out.append(
            ProductBalance(
                product_guid=guid,
                surplus_islands=tuple(sorted(surplus.get(guid, []))),
                deficit_islands=tuple(sorted(deficit.get(guid, []))),
                net_slope_per_min=net[guid],
            )
        )
    out.sort(key=lambda p: -p.net_slope_per_min)
    return out


def display_runway_rows(
    runways: Iterable[IslandProductRunway],
    items: dict[int, Item] | object,
    locale: str = "en",
) -> list[dict[str, object]]:
    """runway list を dict に展開する presenter．HTML/CSV export で流用．

    ``items`` は ``ItemDictionary`` でも plain ``dict[int, Item]`` でも OK．
    """
    out: list[dict[str, object]] = []
    for r in runways:
        try:
            product_name = items[r.product_guid].display_name(locale)  # type: ignore[index]
        except (KeyError, AttributeError):
            product_name = f"Good_{r.product_guid}"
        out.append(
            {
                "island_name": r.island_name,
                "product_guid": r.product_guid,
                "product_name": product_name,
                "latest": r.latest,
                "slope_per_min": round(r.slope_per_min, 3),
                "runway_min": (round(r.runway_min, 1) if r.runway_min is not None else None),
                "status": r.status,
            }
        )
    return out
