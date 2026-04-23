"""Decision Matrix — 書記長本命の処方箋エンジン (v0.5-H #88)．

B-G の全分析 (balance / persistence / correlation / routes) を合成し，
書記長の 3 分類を rule-based で判定する:

| 観測 | 判定 | action |
|---|---|---|
| 慢性 deficit × 高満足度 × 航路あり | 生産増一択 | ``increase_production`` |
| 一過性 deficit × 低相関 × 航路弱い | 取引・融通 | ``trade_flex`` |
| 航路強いのに deficit 残る | 商品構成見直し | ``rebalance_mix`` |
| 黒字 / deficit 解決済 | — | ``ok`` |
| データ不足 | — | ``monitor`` |

Rule threshold は module 定数で公開して書記長がチューニングできるように．
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from anno_save_analyzer.trade.storage import IslandStorageTrend

from .correlation import saturation_vs_deficit
from .frames import AnalysisFrames
from .persistence import classify_deficit
from .routes import rank_routes


@dataclass(frozen=True)
class Thresholds:
    """Decision rule の閾値．``diagnose`` に渡して上書き可．"""

    high_saturation: float = 0.70
    low_saturation: float = 0.40
    low_correlation: float = 0.30
    strong_route_tons_per_min: float = 1.0
    chronic_categories: frozenset[str] = frozenset({"chronic"})
    transient_categories: frozenset[str] = frozenset({"transient"})


_OUTPUT_COLUMNS = [
    "area_manager",
    "city_name",
    "product_guid",
    "product_name",
    "category",
    "action",
    "rationale",
]


def diagnose(
    frames: AnalysisFrames,
    *,
    storage_by_island: Mapping[str, list[IslandStorageTrend]] | None = None,
    thresholds: Thresholds | None = None,
) -> pd.DataFrame:
    """B-G の analyzer を統合して 1 (island, product) 単位で処方箋を出す．

    ``storage_by_island`` を渡すと persistence 判定に使える．未指定 (JSON
    export 単独など) の場合は persistence=unknown として rule が簡略化される．
    """
    th = thresholds or Thresholds()
    balance = frames.balance
    if balance.empty:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    persistence_df = _persistence_by_product(storage_by_island)
    correlation_df = saturation_vs_deficit(frames)
    routes_df = rank_routes(frames.trade_events)
    strong_routes_products = _strong_route_products(frames.trade_events, routes_df, th)

    merged = balance.merge(
        frames.islands[["area_manager", "avg_saturation_mean"]],
        on="area_manager",
        how="left",
    )

    rows: list[dict] = []
    for _, row in merged.iterrows():
        rec = _classify_single(
            row=row,
            persistence_df=persistence_df,
            correlation_df=correlation_df,
            strong_routes_products=strong_routes_products,
            thresholds=th,
        )
        rows.append(rec)
    return pd.DataFrame(rows, columns=_OUTPUT_COLUMNS)


# ---------- internals ----------


def _persistence_by_product(
    storage_by_island: Mapping[str, list[IslandStorageTrend]] | None,
) -> pd.DataFrame:
    if not storage_by_island:
        return pd.DataFrame(columns=["island_name", "product_guid", "category"])
    classified = classify_deficit(storage_by_island)
    return (
        classified[["island_name", "product_guid", "category"]]
        if not classified.empty
        else classified
    )


def _strong_route_products(
    trade_events_df: pd.DataFrame,
    routes_df: pd.DataFrame,
    th: Thresholds,
) -> set[tuple[str, int]]:
    """強い route が到達する ``(island_name, product_guid)`` の集合を返す．"""
    if trade_events_df.empty or routes_df.empty:
        return set()
    strong = routes_df[routes_df["tons_per_min"] >= th.strong_route_tons_per_min]
    if strong.empty:
        return set()
    strong_route_ids = set(strong["route_id"].dropna())
    events = trade_events_df[trade_events_df["route_id"].isin(strong_route_ids)].copy()
    if events.empty:
        return set()
    events = events[events["island_name"].notna()].copy()
    product_guid_numeric = pd.to_numeric(events["product_guid"], errors="coerce")
    valid = product_guid_numeric.notna()
    events = events[valid]
    product_guid = product_guid_numeric[valid].astype(int)
    return set(
        zip(
            events["island_name"].astype(str),
            product_guid,
            strict=False,
        )
    )


def _classify_single(
    *,
    row: pd.Series,
    persistence_df: pd.DataFrame,
    correlation_df: pd.DataFrame,
    strong_routes_products: set[tuple[str, int]],
    thresholds: Thresholds,
) -> dict:
    area_manager = row["area_manager"]
    city_name = row["city_name"]
    product_guid = int(row["product_guid"])
    product_name = row["product_name"]
    delta = float(row["delta_per_minute"])
    saturation = row.get("avg_saturation_mean")

    base = {
        "area_manager": area_manager,
        "city_name": city_name,
        "product_guid": product_guid,
        "product_name": product_name,
    }
    if delta >= 0:
        return {
            **base,
            "category": "ok",
            "action": "none",
            "rationale": f"黒字 (delta=+{delta:.2f}/min)",
        }

    persistence = _persistence_for(persistence_df, city_name or area_manager, product_guid)
    correlation = _correlation_for(correlation_df, product_guid)
    route_key = city_name if city_name is not None else area_manager
    has_strong_route = (str(route_key), product_guid) in strong_routes_products

    # Rule 1: 慢性 deficit × 高満足度 × 運べてる → 生産増一択
    if (
        persistence in thresholds.chronic_categories
        and saturation is not None
        and pd.notna(saturation)
        and saturation >= thresholds.high_saturation
        and has_strong_route
    ):
        return {
            **base,
            "category": "increase_production",
            "action": "build_more_factories",
            "rationale": (
                f"慢性 deficit (持続 {persistence}), 満足度高 ({saturation:.2f}), "
                f"航路は機能中 → 生産能力不足"
            ),
        }

    # Rule 2: 一過性 deficit × 低相関 × 航路弱い → 取引・融通
    if (
        persistence in thresholds.transient_categories
        and correlation is not None
        and pd.notna(correlation)
        and abs(correlation) < thresholds.low_correlation
        and not has_strong_route
    ):
        return {
            **base,
            "category": "trade_flex",
            "action": "short_term_trade_or_route_tweak",
            "rationale": (
                f"一過性 deficit ({persistence}), saturation との相関弱 "
                f"(|r|={abs(correlation):.2f}), 航路は未整備 → 短期融通"
            ),
        }

    # Rule 3: 航路強いのに deficit 残る → 商品構成見直し
    if has_strong_route and delta < 0:
        return {
            **base,
            "category": "rebalance_mix",
            "action": "adjust_loadout",
            "rationale": f"航路は機能しているが delta={delta:.2f}/min → 輸送品目の構成見直し",
        }

    return {
        **base,
        "category": "monitor",
        "action": "watch",
        "rationale": (
            f"delta={delta:.2f}/min, persistence={persistence or 'unknown'}, "
            f"saturation={'nan' if saturation is None or pd.isna(saturation) else f'{saturation:.2f}'} "
            "→ rule 適用外．継続観察推奨"
        ),
    }


def _persistence_for(df: pd.DataFrame, island_name: str | None, product_guid: int) -> str | None:
    if df.empty or island_name is None:
        return None
    mask = (df["island_name"] == island_name) & (df["product_guid"] == product_guid)
    row = df[mask]
    if row.empty:
        return None
    return str(row.iloc[0]["category"])


def _correlation_for(df: pd.DataFrame, product_guid: int) -> float | None:
    if df.empty:
        return None
    mask = df["product_guid"] == product_guid
    row = df[mask]
    if row.empty:
        return None
    value = row.iloc[0]["pearson_r"]
    return float(value) if pd.notna(value) else None
