"""VRP (Vehicle Routing Problem) 最適化 — v0.5 最終本丸 (#13)．

OR-Tools ``RoutingModel`` を使って **物資ごとの pickup-and-delivery VRP**
を解く．船数 + capacity + 距離 heuristic の制約で各 vehicle の経路を
決定し，Min-Cost Flow より現実的な「船何隻でどう回るか」の計画を返す．

## 設計

各物資を独立に解く (物資間の船共有はしない MVP)．理由:

- Anno では物資種別ごとに船が区別されることが多い (Schooner が食料，
  Clipper が工業品など)
- 物資混載は save から取れない情報 (ship のカーゴ構成は内部保存されず)
- 物資独立にすれば各 product の VRP は小規模で OR-Tools が即解ける

各物資について:

1. depot (仮想) + supplier ノード + demander ノードを持つ graph
2. supplier は「pickup」，demander は「delivery」．RoutingModel の
   pickups_and_deliveries 制約で pair 化
3. 距離 matrix は session_by_area_manager (同 session=1 / 別=10)
4. 各 vehicle のカーゴ capacity 制約 + 船数制約

## 出力

- ``routes``: 解けた vehicle 経路のリスト (空 route は除外)
- ``unmet_demand``: capacity / 船数不足で割当られなかった需要
- ``objective_value``: 総距離 (コスト和)
- ``solve_status``: OR-Tools の solution status
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

_SCALE = 1000
_SAME_SESSION = 1
_DIFFERENT_SESSION = 10


@dataclass(frozen=True)
class OptimizedStop:
    """1 経路 1 stop．pickup か delivery を区別．"""

    area_manager: str
    kind: str  # "pickup" / "delivery"
    product_guid: int
    quantity_per_min: float


@dataclass(frozen=True)
class OptimizedRoute:
    """1 vehicle が回る経路．``stops`` は訪問順．"""

    vehicle_id: int
    product_guid: int
    product_name: str
    stops: tuple[OptimizedStop, ...]
    total_distance: int


@dataclass(frozen=True)
class UnmetDemand:
    """解けなかった需要．"""

    area_manager: str
    product_guid: int
    product_name: str
    quantity_per_min: float


@dataclass(frozen=True)
class OptimizedPlan:
    """VRP 全体の解．"""

    routes: tuple[OptimizedRoute, ...]
    unmet_demand: tuple[UnmetDemand, ...]
    objective_value: int
    solve_status: str


def optimize_routes(
    balance_df: pd.DataFrame,
    *,
    n_vehicles: int = 5,
    vehicle_capacity: int = 100,
    session_by_area_manager: Mapping[str, str] | None = None,
    time_limit_seconds: int = 10,
) -> OptimizedPlan:
    """物資ごとに PDP-VRP を解いて輸送計画を返す．

    ``vehicle_capacity`` は 1 trip で運べる tons (scaled 値ではなく人間に
    わかりやすい tons 単位)．``time_limit_seconds`` は各物資の solve
    時間上限．
    """
    if balance_df.empty:
        return OptimizedPlan(
            routes=(), unmet_demand=(), objective_value=0, solve_status="empty_input"
        )

    all_routes: list[OptimizedRoute] = []
    all_unmet: list[UnmetDemand] = []
    total_objective = 0
    last_status = "no_products"

    for (guid, name), group in balance_df.groupby(["product_guid", "product_name"]):
        suppliers = group[group["delta_per_minute"] > 0]
        demanders = group[group["delta_per_minute"] < 0]
        if suppliers.empty or demanders.empty:
            continue
        result = _solve_product(
            product_guid=int(guid),
            product_name=str(name),
            suppliers=suppliers,
            demanders=demanders,
            n_vehicles=n_vehicles,
            vehicle_capacity=vehicle_capacity,
            session_map=session_by_area_manager or {},
            time_limit_seconds=time_limit_seconds,
        )
        all_routes.extend(result.routes)
        all_unmet.extend(result.unmet_demand)
        total_objective += result.objective_value
        last_status = result.solve_status

    return OptimizedPlan(
        routes=tuple(all_routes),
        unmet_demand=tuple(all_unmet),
        objective_value=total_objective,
        solve_status=last_status,
    )


def _solve_product(
    *,
    product_guid: int,
    product_name: str,
    suppliers: pd.DataFrame,
    demanders: pd.DataFrame,
    n_vehicles: int,
    vehicle_capacity: int,
    session_map: Mapping[str, str],
    time_limit_seconds: int,
) -> OptimizedPlan:
    """1 物資分の PDP-VRP を OR-Tools で解く．"""
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    supplier_nodes: list[tuple[str, int]] = [
        (str(row["area_manager"]), int(float(row["delta_per_minute"]) * _SCALE))
        for _, row in suppliers.iterrows()
    ]
    demander_nodes: list[tuple[str, int]] = [
        (str(row["area_manager"]), int(-float(row["delta_per_minute"]) * _SCALE))
        for _, row in demanders.iterrows()
    ]

    # Nodes: [depot, *suppliers, *demanders]
    depot_index = 0
    supplier_start = 1
    supplier_end = supplier_start + len(supplier_nodes)
    demander_start = supplier_end
    demander_end = demander_start + len(demander_nodes)
    n_nodes = demander_end

    area_manager_by_node: dict[int, str] = {
        depot_index: "__depot__",
    }
    for i, (am, _) in enumerate(supplier_nodes):
        area_manager_by_node[supplier_start + i] = am
    for i, (am, _) in enumerate(demander_nodes):
        area_manager_by_node[demander_start + i] = am

    # 距離 matrix (depot は全島に cost=0 で接続 — 船出発点の抽象化)
    def node_session(idx: int) -> str | None:
        if idx == depot_index:
            return None
        am = area_manager_by_node[idx]
        return session_map.get(am)

    distance = [[0] * n_nodes for _ in range(n_nodes)]
    for i in range(n_nodes):
        for j in range(n_nodes):
            if i == j or depot_index in (i, j):
                distance[i][j] = 0
                continue
            si, sj = node_session(i), node_session(j)
            if si is None or sj is None:
                distance[i][j] = _SAME_SESSION
            else:
                distance[i][j] = _SAME_SESSION if si == sj else _DIFFERENT_SESSION

    # Demands: supplier は正 (pickup), demander は負 (delivery)
    demands: list[int] = [0] * n_nodes
    for i, (_, qty) in enumerate(supplier_nodes):
        demands[supplier_start + i] = qty
    for i, (_, qty) in enumerate(demander_nodes):
        demands[demander_start + i] = -qty

    manager = pywrapcp.RoutingIndexManager(n_nodes, n_vehicles, depot_index)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index: int, to_index: int) -> int:
        return distance[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    transit_idx = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    # Capacity 制約: cumulative demand が +/- vehicle_capacity_scaled を超えない
    cap_scaled = vehicle_capacity * _SCALE

    def demand_callback(from_index: int) -> int:
        return demands[manager.IndexToNode(from_index)]

    demand_idx = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_idx,
        0,
        [cap_scaled] * n_vehicles,
        True,  # start cumul at zero
        "Capacity",
    )

    # Pickup and delivery pairs: 各 supplier / demander を pair 化
    # MVP: 全 supplier × 全 demander の pair を許容 (supplier N × demander M 個)
    # → OR-Tools の pickup-delivery 制約は 1:1 pair 必須なので，分割が要る
    # 簡易化: supplier と demander の node を個別に訪問可 (VRP with demands)
    # とし，capacity と transit で近似解を出す．
    # (厳密 PDPTW は node splitting が重いので後続 issue で拡張)

    # Allow dropping nodes with penalty (capacity 不足時 unmet に回す)
    penalty = 10**9
    for i in range(supplier_start, demander_end):
        routing.AddDisjunction([manager.NodeToIndex(i)], penalty)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.time_limit.FromSeconds(time_limit_seconds)

    solution = routing.SolveWithParameters(search_parameters)
    if solution is None:
        return OptimizedPlan(
            routes=(), unmet_demand=(), objective_value=0, solve_status="no_solution"
        )

    routes: list[OptimizedRoute] = []
    visited_nodes: set[int] = set()
    for vehicle_id in range(n_vehicles):
        stops: list[OptimizedStop] = []
        total_dist = 0
        index = routing.Start(vehicle_id)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node != depot_index:
                visited_nodes.add(node)
                if supplier_start <= node < supplier_end:
                    supp_am, qty = supplier_nodes[node - supplier_start]
                    stops.append(
                        OptimizedStop(
                            area_manager=supp_am,
                            kind="pickup",
                            product_guid=product_guid,
                            quantity_per_min=qty / _SCALE,
                        )
                    )
                elif demander_start <= node < demander_end:
                    dem_am, qty = demander_nodes[node - demander_start]
                    stops.append(
                        OptimizedStop(
                            area_manager=dem_am,
                            kind="delivery",
                            product_guid=product_guid,
                            quantity_per_min=qty / _SCALE,
                        )
                    )
            next_index = solution.Value(routing.NextVar(index))
            total_dist += routing.GetArcCostForVehicle(index, next_index, vehicle_id)
            index = next_index
        if stops:
            routes.append(
                OptimizedRoute(
                    vehicle_id=vehicle_id,
                    product_guid=product_guid,
                    product_name=product_name,
                    stops=tuple(stops),
                    total_distance=total_dist,
                )
            )

    # Unmet demand: 訪問されなかった demander
    unmet: list[UnmetDemand] = []
    for i, (am, qty) in enumerate(demander_nodes):
        if (demander_start + i) not in visited_nodes:
            unmet.append(
                UnmetDemand(
                    area_manager=am,
                    product_guid=product_guid,
                    product_name=product_name,
                    quantity_per_min=qty / _SCALE,
                )
            )

    return OptimizedPlan(
        routes=tuple(routes),
        unmet_demand=tuple(unmet),
        objective_value=solution.ObjectiveValue(),
        solve_status="ok",
    )
