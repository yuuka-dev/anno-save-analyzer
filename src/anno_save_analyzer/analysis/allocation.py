"""需給ギャップの最適割当 (v0.5-I #89)．

供給余剰島 → 赤字島への物資分配を ``networkx.max_flow_min_cost`` で解く．
全 demand を満たせない場合は partial flow を返す．

## Graph 構造 (物資ごと)

```
SRC → supplier_1 (cap=excess_1) ──┐
                                  ├─→ demander_1 (cap=need_1) → SNK
SRC → supplier_2 (cap=excess_2) ──┤                                ↑
                                  └─→ demander_2 (cap=need_2) ────┘
```

- ``SRC → supplier`` の cap = 供給余剰
- ``demander → SNK`` の cap = 不足量
- ``supplier → demander`` は無限 cap，cost は距離 proxy

## 距離 proxy

``session_by_area_manager`` が渡されれば session 一致で cost=1，不一致で
cost=10．未指定なら全 edge cost=1 (距離区別なし)．
"""

from __future__ import annotations

from collections.abc import Mapping

import networkx as nx
import pandas as pd

_SCALE = 1000  # 小数を整数化するスケール．networkx は int capacity 前提
_SAME_SESSION_COST = 1
_DIFFERENT_SESSION_COST = 10

_OUTPUT_COLUMNS = [
    "product_guid",
    "product_name",
    "source_am",
    "sink_am",
    "quantity_per_min",
    "cost",
]


def optimal_flow(
    balance_df: pd.DataFrame,
    *,
    session_by_area_manager: Mapping[str, str | None] | None = None,
) -> pd.DataFrame:
    """各物資の供給余剰→赤字 flow を min-cost で解く．

    ``balance_df`` は ``analysis.frames.to_frames(state).balance`` の形式を
    想定．``delta_per_minute > 0`` = 供給余剰，``< 0`` = 赤字として扱う．

    戻り値: 1 row = 1 (product, source, sink) 割当．flow=0 の組は省略．
    """
    if balance_df.empty:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    session_map: Mapping[str, str | None] = session_by_area_manager or {}
    rows: list[dict] = []
    for (guid, name), group in balance_df.groupby(["product_guid", "product_name"]):
        suppliers = group[group["delta_per_minute"] > 0]
        demanders = group[group["delta_per_minute"] < 0]
        if suppliers.empty or demanders.empty:
            continue
        flow_dict = _solve_product(
            suppliers=suppliers,
            demanders=demanders,
            session_by_area_manager=session_map,
        )
        for source_am, sink_am, flow_scaled in flow_dict:
            cost = _edge_cost(source_am, sink_am, session_map)
            rows.append(
                {
                    "product_guid": int(guid),
                    "product_name": name,
                    "source_am": source_am,
                    "sink_am": sink_am,
                    "quantity_per_min": flow_scaled / _SCALE,
                    "cost": cost,
                }
            )
    return (
        pd.DataFrame(rows, columns=_OUTPUT_COLUMNS)
        .sort_values(["product_name", "source_am", "sink_am"])
        .reset_index(drop=True)
    )


# ---------- internals ----------


def _solve_product(
    *,
    suppliers: pd.DataFrame,
    demanders: pd.DataFrame,
    session_by_area_manager: Mapping[str, str | None],
) -> list[tuple[str, str, int]]:
    """1 物資について max-flow min-cost を解いて (source, sink, flow) を返す．"""
    g = nx.DiGraph()
    src_node = "__SRC__"
    sink_node = "__SNK__"
    g.add_node(src_node)
    g.add_node(sink_node)

    for _, row in suppliers.iterrows():
        am = str(row["area_manager"])
        cap = int(round(float(row["delta_per_minute"]) * _SCALE))
        if cap <= 0:
            continue
        g.add_edge(src_node, _supplier_node(am), capacity=cap, weight=0)

    for _, row in demanders.iterrows():
        am = str(row["area_manager"])
        cap = int(round(-float(row["delta_per_minute"]) * _SCALE))
        if cap <= 0:
            continue
        g.add_edge(_demander_node(am), sink_node, capacity=cap, weight=0)

    for _, sup in suppliers.iterrows():
        sup_am = str(sup["area_manager"])
        for _, dem in demanders.iterrows():
            dem_am = str(dem["area_manager"])
            weight = _edge_cost(sup_am, dem_am, session_by_area_manager)
            g.add_edge(
                _supplier_node(sup_am),
                _demander_node(dem_am),
                capacity=10**9,
                weight=weight,
            )

    try:
        flow = nx.max_flow_min_cost(g, src_node, sink_node)
    except nx.NetworkXUnfeasible:  # pragma: no cover - defensive
        return []

    results: list[tuple[str, str, int]] = []
    for u, outs in flow.items():
        if not u.startswith("S::"):
            continue
        sup_am = u[3:]
        for v, amount in outs.items():
            if not v.startswith("D::") or amount <= 0:
                continue
            dem_am = v[3:]
            results.append((sup_am, dem_am, int(amount)))
    return results


def _supplier_node(area_manager: str) -> str:
    return f"S::{area_manager}"


def _demander_node(area_manager: str) -> str:
    return f"D::{area_manager}"


def _edge_cost(
    source_am: str,
    sink_am: str,
    session_by_area_manager: Mapping[str, str | None],
) -> int:
    if not session_by_area_manager:
        return _SAME_SESSION_COST
    src_session = session_by_area_manager.get(source_am)
    sink_session = session_by_area_manager.get(sink_am)
    if src_session is None or sink_session is None:
        return _SAME_SESSION_COST
    return _SAME_SESSION_COST if src_session == sink_session else _DIFFERENT_SESSION_COST
