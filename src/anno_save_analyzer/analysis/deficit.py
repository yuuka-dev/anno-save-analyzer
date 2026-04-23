"""Deficit heatmap と Pareto (ABC) 分析．

書記長の「島×商品 deficit マップ」視覚化用．``balance`` DataFrame を
pivot して島×物資の delta マトリクスを作り，Pareto で重要物資を絞る．
"""

from __future__ import annotations

import pandas as pd

_PARETO_A_CUTOFF = 0.80
_PARETO_B_CUTOFF = 0.95


def deficit_heatmap(balance_df: pd.DataFrame) -> pd.DataFrame:
    """島 (index) × 物資 (columns) の delta_per_minute マトリクス．

    値が負 = 赤字．``fill_value=0`` で空欄は 0 (=消費も生産も無い)．
    空入力は空 DataFrame を返す．
    """
    if balance_df.empty:
        return pd.DataFrame()
    return balance_df.pivot_table(
        index="area_manager",
        columns="product_name",
        values="delta_per_minute",
        aggfunc="sum",
        fill_value=0.0,
    )


def pareto(
    balance_df: pd.DataFrame,
    metric: str = "consumed_per_minute",
) -> pd.DataFrame:
    """物資別 総量降順 + ABC ランク付け．

    累積寄与率 <= 80% = ``A`` / <=95% = ``B`` / 残り = ``C``．書記長が
    deficit 対策の優先順位付けに使う．``metric`` は ``consumed_per_minute`` /
    ``produced_per_minute`` / ``delta_per_minute`` などを想定．
    """
    columns = ["product_guid", "product_name", metric, "cum_share", "abc_rank"]
    if balance_df.empty or metric not in balance_df.columns:
        return pd.DataFrame(columns=columns)

    grouped = (
        balance_df.groupby(["product_guid", "product_name"], as_index=False)[metric]
        .sum()
        .sort_values(metric, ascending=False, key=lambda s: s.abs())
        .reset_index(drop=True)
    )
    total = grouped[metric].abs().sum()
    if total == 0:
        grouped["cum_share"] = 0.0
        grouped["abc_rank"] = "C"
        return grouped[columns]
    grouped["cum_share"] = grouped[metric].abs().cumsum() / total
    grouped["abc_rank"] = grouped["cum_share"].apply(_abc_label)
    return grouped[columns]


def _abc_label(cum_share: float) -> str:
    if cum_share <= _PARETO_A_CUTOFF:
        return "A"
    if cum_share <= _PARETO_B_CUTOFF:
        return "B"
    return "C"
