"""輸送ルート効率ランキング．

書記長「輸送ルート効率ランキング」．trade_events DataFrame を route_id
単位で集計し，1 分あたりの輸送量 / 売上 / イベント密度を計算．
"""

from __future__ import annotations

import pandas as pd

from anno_save_analyzer.trade.clock import TICKS_PER_MINUTE


def rank_routes(trade_events_df: pd.DataFrame) -> pd.DataFrame:
    """route_id でグループ化した効率指標．

    列:
      ``route_id`` / ``route_name`` / ``events_count`` /
      ``unique_products`` / ``total_amount`` / ``total_gold`` /
      ``ticks_span`` / ``tons_per_min`` / ``gold_per_min``

    ``ticks_span`` は events の min/max timestamp_tick の差．
    ``tons_per_min`` / ``gold_per_min`` は正規化 (分換算)．
    """
    columns = [
        "route_id",
        "route_name",
        "events_count",
        "unique_products",
        "total_amount",
        "total_gold",
        "ticks_span",
        "tons_per_min",
        "gold_per_min",
    ]
    if trade_events_df.empty:
        return pd.DataFrame(columns=columns)

    df = trade_events_df.copy()
    df = df[df["route_id"].notna()]
    if df.empty:
        return pd.DataFrame(columns=columns)

    agg = (
        df.groupby("route_id")
        .agg(
            route_name=("route_name", "first"),
            events_count=("product_guid", "size"),
            unique_products=("product_guid", "nunique"),
            total_amount=("amount", "sum"),
            total_gold=("total_price", "sum"),
            tick_min=("timestamp_tick", "min"),
            tick_max=("timestamp_tick", "max"),
        )
        .reset_index()
    )
    agg["ticks_span"] = (agg["tick_max"] - agg["tick_min"]).fillna(0).astype("Int64")
    minutes = agg["ticks_span"].astype(float) / TICKS_PER_MINUTE
    # 0 割り避け: minutes == 0 は events_count をそのまま /min 換算相当として使う
    agg["tons_per_min"] = (
        (agg["total_amount"].astype(float) / minutes).where(minutes > 0, 0.0).fillna(0.0)
    )
    agg["gold_per_min"] = (
        (agg["total_gold"].astype(float) / minutes).where(minutes > 0, 0.0).fillna(0.0)
    )
    return agg[columns].sort_values("tons_per_min", ascending=False).reset_index(drop=True)
