"""満足度 × 不足 相関分析．

書記長「満足度ダウン要因 × 商品不足の相関」．各物資について島の
``avg_saturation_mean`` と ``delta_per_minute`` の Pearson / Spearman
相関を計算．負の相関 = 「不足するほど満足度下がる」主因物資候補．
"""

from __future__ import annotations

import pandas as pd

from .frames import AnalysisFrames


def saturation_vs_deficit(frames: AnalysisFrames) -> pd.DataFrame:
    """物資別に (pearson, spearman, sample_size) を返す．

    sample_size が 3 未満の物資は相関を NaN にして静かに返す (統計的に
    弱すぎる → 後段で filter する設計)．
    """
    columns = ["product_guid", "product_name", "pearson_r", "spearman_r", "sample_size"]
    if frames.balance.empty or frames.islands.empty:
        return pd.DataFrame(columns=columns)
    merged = frames.balance.merge(
        frames.islands[["area_manager", "avg_saturation_mean"]],
        on="area_manager",
        how="left",
    )
    merged = merged.dropna(subset=["avg_saturation_mean"])

    rows: list[dict] = []
    for (guid, name), group in merged.groupby(["product_guid", "product_name"]):
        size = len(group)
        if size < 3:
            pearson_r: float = float("nan")
            spearman_r: float = float("nan")
        else:
            sat = group["avg_saturation_mean"]
            delta = group["delta_per_minute"]
            pearson_r = float(sat.corr(delta, method="pearson"))
            # Spearman = rank 変換後の Pearson．pandas の内蔵 spearman は
            # scipy 必須なので自前実装して scipy への base 依存を避ける．
            spearman_r = float(sat.rank().corr(delta.rank(), method="pearson"))
        rows.append(
            {
                "product_guid": guid,
                "product_name": name,
                "pearson_r": pearson_r,
                "spearman_r": spearman_r,
                "sample_size": size,
            }
        )
    return pd.DataFrame(rows, columns=columns)
