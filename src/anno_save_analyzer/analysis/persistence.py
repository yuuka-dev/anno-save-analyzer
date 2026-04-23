"""慢性 vs 一過性の deficit 分類．

StorageTrends の 120 点時系列を舐めて，在庫 0 (= 欠品) の頻度から
``chronic`` / ``transient`` / ``stable`` を判定．書記長の Decision Matrix
(#88) の入力になる．
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import pandas as pd

from anno_save_analyzer.trade.storage import IslandStorageTrend

_CHRONIC_RATIO = 0.50
_TRANSIENT_RATIO = 0.10


def classify_deficit(
    storage_by_island: Mapping[str, Iterable[IslandStorageTrend]],
) -> pd.DataFrame:
    """島 × 物資の deficit 持続性分類．

    列:
      ``island_name`` / ``product_guid`` / ``stockout_ratio`` /
      ``latest`` / ``peak`` / ``mean`` / ``slope`` / ``category``

    ``stockout_ratio`` = samples 中の値 0 の割合．1.0 に近いほど慢性．
    ``category``:
      - ``chronic``  : ratio >= 0.50
      - ``transient``: 0.10 <= ratio < 0.50
      - ``stable``   : < 0.10 (実質欠品なし)
    """
    columns = [
        "island_name",
        "product_guid",
        "stockout_ratio",
        "latest",
        "peak",
        "mean",
        "slope",
        "category",
    ]
    rows: list[dict] = []
    for island_name, trends in storage_by_island.items():
        for t in trends:
            samples = t.points.samples
            n = len(samples)
            stockout_ratio = sum(1 for v in samples if v == 0) / n if n else 0.0
            rows.append(
                {
                    "island_name": island_name,
                    "product_guid": t.product_guid,
                    "stockout_ratio": stockout_ratio,
                    "latest": t.points.latest,
                    "peak": t.points.peak,
                    "mean": t.points.mean,
                    "slope": t.points.slope,
                    "category": _categorize(stockout_ratio),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def _categorize(stockout_ratio: float) -> str:
    if stockout_ratio >= _CHRONIC_RATIO:
        return "chronic"
    if stockout_ratio >= _TRANSIENT_RATIO:
        return "transient"
    return "stable"
