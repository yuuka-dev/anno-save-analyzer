"""「船 1 隻減らす」感度分析 (leave-one-out)．

書記長「船1隻減らすならどこ？」．TradeEvent ledger から各 route の
輸送寄与を集計し，1 route ずつ除外した時に影響を受ける島を特定する．
簡易 MVP: TradeEvent の route 別 volume を現 balance から「差し引いた」
仮想 delta で deficit 増加数を数える．
"""

from __future__ import annotations

import pandas as pd

from anno_save_analyzer.trade.clock import TICKS_PER_MINUTE

from .frames import AnalysisFrames


def route_leave_one_out(frames: AnalysisFrames) -> pd.DataFrame:
    """各 route を除外した時の「追加 deficit 物資数」．

    列:
      ``route_id`` / ``route_name`` / ``tons_per_min`` / ``affected_products`` /
      ``added_deficit_count`` / ``recommended_action``

    仮定:
      route の輸送量 ``tons_per_min`` は history から推定．route 除外は
      「到着島で ``consumed`` が発生しなくなる = delta に + 加算」と近似．
      (実体は生産地側の余剰で補填されるので双方影響だが MVP は消費地側のみ)．

    ``recommended_action``:
      - ``safe_to_remove``: added_deficit_count == 0
      - ``impacts_<N>_products``: N > 0

    rows=0 の場合 (events 無し) は空 DataFrame．
    """
    columns = [
        "route_id",
        "route_name",
        "tons_per_min",
        "affected_products",
        "added_deficit_count",
        "recommended_action",
    ]
    events = frames.trade_events
    balance = frames.balance
    if events.empty or balance.empty:
        return pd.DataFrame(columns=columns)

    routed = events[events["route_id"].notna()].copy()
    if routed.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict] = []
    for route_id, group in routed.groupby("route_id"):
        route_name = group["route_name"].iloc[0]
        max_tick = group["timestamp_tick"].max()
        min_tick = group["timestamp_tick"].min()
        tick_span = 0.0 if pd.isna(max_tick) or pd.isna(min_tick) else float(max_tick - min_tick)
        minutes = max(1.0, tick_span / TICKS_PER_MINUTE)
        tons_per_min = float(group["amount"].sum()) / minutes

        # route が運んでる unique products
        products = group["product_guid"].unique().tolist()
        route_islands = set(group["island_name"].dropna())
        route_area_managers: set[str] = set()
        if (
            route_islands
            and not frames.islands.empty
            and "city_name" in frames.islands
            and "area_manager" in frames.islands
        ):
            route_area_managers = set(
                frames.islands.loc[
                    frames.islands["city_name"].isin(route_islands), "area_manager"
                ].dropna()
            )

        # その島 × 物資の現在 balance で「delta - tons_per_min/len(products)」を
        # 減算した場合に deficit 化するものを数える (均等分担仮定の MVP)
        added_deficit = 0
        per_product_contribution = tons_per_min / len(products) if products else 0.0
        for product_guid in products:
            mask = balance["product_guid"] == product_guid
            location_mask = pd.Series(False, index=balance.index)
            if "city_name" in balance and route_islands:
                location_mask |= balance["city_name"].isin(route_islands)
            if "area_manager" in balance and route_area_managers:
                location_mask |= balance["area_manager"].isin(route_area_managers)
            if location_mask.any():
                mask &= location_mask
            for _, row in balance[mask].iterrows():
                # 「route 除外 = 消費地に届かない」→ その分 供給量が減る
                # 近似: delta_new = delta - per_product_contribution (赤字悪化方向)
                # ここでは route が消費地に供給する想定なので delta から引く
                old_delta = row["delta_per_minute"]
                simulated = old_delta - per_product_contribution
                was_deficit = old_delta < 0
                now_deficit = simulated < 0
                if now_deficit and not was_deficit:
                    added_deficit += 1
        recommended = (
            "safe_to_remove" if added_deficit == 0 else f"impacts_{added_deficit}_products"
        )
        rows.append(
            {
                "route_id": route_id,
                "route_name": route_name,
                "tons_per_min": tons_per_min,
                "affected_products": len(products),
                "added_deficit_count": added_deficit,
                "recommended_action": recommended,
            }
        )
    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values(["added_deficit_count", "tons_per_min"], ascending=[True, True])
        .reset_index(drop=True)
    )
