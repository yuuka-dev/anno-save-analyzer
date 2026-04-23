"""人口成長 / 消費 予測．

Logistic Growth (S-curve) は時系列データが要るが現 save は単一 snapshot
なので MVP では:

1. ``consumption_forecast``: 現 delta_per_minute が N 時間続いたら累積
   不足量はいくら? の線形投影．短期 (24h 以内) には妥当．
2. ``population_capacity_proxy``: ``full_house`` と ``residence_count`` から
   「あと何人入れられるか」の空き capacity を簡単に出す．logistic の
   ``carrying_capacity`` 代替．

時系列 logistic fit は別 issue で複数 snapshot を読み込む機構ができた後．
"""

from __future__ import annotations

import pandas as pd

from .frames import AnalysisFrames


def consumption_forecast(frames: AnalysisFrames, hours_ahead: float = 6.0) -> pd.DataFrame:
    """現状の delta が ``hours_ahead`` 時間持続した場合の累積不足量．

    ``delta_per_minute`` × ``minutes`` で単純線形投影．``projected_delta_total``
    が負 = その物資はその時間で赤字累積．
    """
    columns = [
        "area_manager",
        "city_name",
        "product_guid",
        "product_name",
        "delta_per_minute",
        "projected_delta_total",
    ]
    if frames.balance.empty:
        return pd.DataFrame(columns=columns)
    minutes = hours_ahead * 60.0
    df = frames.balance.copy()
    df["projected_delta_total"] = df["delta_per_minute"] * minutes
    return df[columns].sort_values("projected_delta_total").reset_index(drop=True)


def population_capacity_proxy(frames: AnalysisFrames, per_house: int = 10) -> pd.DataFrame:
    """住居あたり最大人数から「空き capacity」を推定．

    ``per_house=10`` は Farmer の ``fullHouse``．実際は tier ごとに違うので
    tier breakdown が必要だが MVP は均等 proxy．正確版は後続 PR．
    """
    columns = [
        "area_manager",
        "city_name",
        "resident_total",
        "residence_count",
        "capacity_est",
        "headroom",
        "headroom_ratio",
    ]
    if frames.islands.empty:
        return pd.DataFrame(columns=columns)
    df = frames.islands.copy()
    df["capacity_est"] = df["residence_count"] * per_house
    df["headroom"] = (df["capacity_est"] - df["resident_total"]).clip(lower=0)
    df["headroom_ratio"] = (df["headroom"] / df["capacity_est"]).where(df["capacity_est"] > 0, 0.0)
    return df[columns].reset_index(drop=True)
