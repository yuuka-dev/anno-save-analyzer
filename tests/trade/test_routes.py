"""``trade.routes.list_trade_routes`` の単体テスト．

テスト用の minimal_v3 fixture は ``ConstructionAI > TradeRoute > TradeRoutes > <1>``
の階層を組み立て，実セーブの構造を模倣する．
"""

from __future__ import annotations

import struct

from anno_save_analyzer.trade import (
    TradeRouteDef,
    TransportTask,
    list_trade_routes,
)
from tests.parser.filedb.conftest import Event, minimal_v3

_TAGS = {
    2: "ConstructionAI",
    3: "TradeRoute",
    4: "TradeRoutes",
    5: "TransportTasks",
    6: "TransportType",
    7: "RouteType",
}
_ATTRIBS = {
    0x8001: "Route",
    0x8002: "ShipID",
    0x8003: "RoundTravel",
    0x8004: "EstablishTime",
    0x8005: "From",
    0x8006: "To",
    0x8007: "Product",
    0x8008: "Balance",
    0x8009: "id",
}


def _task(from_key: int, to_key: int, product: int, balance: int) -> list[Event]:
    return [
        ("T", 1),  # task <1>
        ("A", 0x8005, struct.pack("<H", from_key)),
        ("A", 0x8006, struct.pack("<H", to_key)),
        ("A", 0x8007, struct.pack("<i", product)),
        ("A", 0x8008, struct.pack("<i", balance)),
        ("T", 6),  # TransportType (nested)
        ("A", 0x8009, b"\x00\x00"),
        ("X",),  # close TransportType
        ("X",),  # close task
    ]


def _route(
    *,
    tasks: list[list[Event]],
    route_hash: int | None = None,
    ship_id: int | None = None,
    round_travel: int | None = None,
    establish_time: int | None = None,
) -> list[Event]:
    events: list[Event] = [("T", 1)]  # route <1>
    if tasks:
        events.append(("T", 5))  # TransportTasks
        for t in tasks:
            events.extend(t)
        events.append(("X",))  # close TransportTasks
    if route_hash is not None:
        events.append(("A", 0x8001, struct.pack("<i", route_hash)))
    if ship_id is not None:
        events.append(("A", 0x8002, struct.pack("<i", ship_id)))
    if round_travel is not None:
        events.append(("A", 0x8003, struct.pack("<q", round_travel)))
    if establish_time is not None:
        events.append(("A", 0x8004, struct.pack("<q", establish_time)))
    events.append(("T", 7))  # RouteType (nested)
    events.append(("A", 0x8009, b"\x00\x00"))
    events.append(("X",))  # close RouteType
    events.append(("X",))  # close route
    return events


def _wrap_ca(routes: list[list[Event]]) -> list[Event]:
    events: list[Event] = [("T", 2), ("T", 3), ("T", 4)]
    for r in routes:
        events.extend(r)
    events.append(("X",))  # close TradeRoutes
    events.append(("X",))  # close TradeRoute
    events.append(("X",))  # close ConstructionAI
    return events


class TestListTradeRoutesHappy:
    def test_extracts_two_routes_with_tasks(self) -> None:
        inner = minimal_v3(
            tags=_TAGS,
            attribs=_ATTRIBS,
            events=_wrap_ca(
                [
                    _route(
                        tasks=[
                            _task(100, 200, product=2143, balance=42),
                            _task(200, 100, product=2149, balance=99),
                        ],
                        route_hash=612443073,
                        ship_id=42,
                        round_travel=688223,
                        establish_time=134622100,
                    ),
                    _route(tasks=[], ship_id=43),
                ]
            ),
        )
        routes = list_trade_routes(inner)
        assert len(routes) == 2
        r1, r2 = routes
        assert r1 == TradeRouteDef(
            ship_id=42,
            route_hash=612443073,
            round_travel=688223,
            establish_time=134622100,
            tasks=(
                TransportTask(from_key=100, to_key=200, product_guid=2143, balance_raw=42),
                TransportTask(from_key=200, to_key=100, product_guid=2149, balance_raw=99),
            ),
        )
        assert r2 == TradeRouteDef(
            ship_id=43, route_hash=None, round_travel=None, establish_time=None, tasks=()
        )

    def test_nested_transport_type_does_not_leak_into_task_attribs(self) -> None:
        """task 配下の TransportType.id (2B) は from_key として拾われない．"""
        inner = minimal_v3(
            tags=_TAGS,
            attribs=_ATTRIBS,
            events=_wrap_ca(
                [
                    _route(tasks=[_task(1, 2, product=3000, balance=7)], ship_id=1),
                ]
            ),
        )
        routes = list_trade_routes(inner)
        assert routes[0].tasks[0].from_key == 1
        assert routes[0].tasks[0].to_key == 2

    def test_multiple_construction_ai_blocks_collected(self) -> None:
        events: list[Event] = []
        events.extend(_wrap_ca([_route(tasks=[], ship_id=10)]))
        events.extend(_wrap_ca([_route(tasks=[], ship_id=20)]))
        inner = minimal_v3(tags=_TAGS, attribs=_ATTRIBS, events=events)
        routes = list_trade_routes(inner)
        assert [r.ship_id for r in routes] == [10, 20]


class TestListTradeRoutesEmpty:
    def test_empty_bytes_returns_empty(self) -> None:
        assert list_trade_routes(b"") == ()

    def test_missing_construction_ai_returns_empty(self) -> None:
        inner = minimal_v3(tags={2: "Other"}, attribs={}, events=[("T", 2), ("X",)])
        assert list_trade_routes(inner) == ()

    def test_missing_trade_route_tag_returns_empty(self) -> None:
        inner = minimal_v3(
            tags={2: "ConstructionAI"},
            attribs={},
            events=[("T", 2), ("X",)],
        )
        assert list_trade_routes(inner) == ()

    def test_missing_trade_routes_tag_returns_empty(self) -> None:
        inner = minimal_v3(
            tags={2: "ConstructionAI", 3: "TradeRoute"},
            attribs={},
            events=[("T", 2), ("T", 3), ("X",), ("X",)],
        )
        assert list_trade_routes(inner) == ()

    def test_no_route_entries_returns_empty(self) -> None:
        """CA > TR > TRs は存在するが entry <1> が無い → 空．"""
        inner = minimal_v3(
            tags=_TAGS,
            attribs=_ATTRIBS,
            events=_wrap_ca([]),
        )
        assert list_trade_routes(inner) == ()

    def test_missing_transport_tasks_tag_keeps_route_empty_tasks(self) -> None:
        """TransportTasks 辞書未登録でも route は抽出される (tasks=())．"""
        tags = {k: v for k, v in _TAGS.items() if v != "TransportTasks"}
        # route 内部に TransportTasks を持たない
        events: list[Event] = [("T", 2), ("T", 3), ("T", 4), ("T", 1)]
        events.append(("A", 0x8002, struct.pack("<i", 7)))  # ShipID
        events.append(("T", 7))  # RouteType
        events.append(("A", 0x8009, b"\x00\x00"))
        events.append(("X",))
        events.append(("X",))  # close route
        events.append(("X",))  # close TradeRoutes
        events.append(("X",))  # close TradeRoute
        events.append(("X",))  # close ConstructionAI
        inner = minimal_v3(tags=tags, attribs=_ATTRIBS, events=events)
        routes = list_trade_routes(inner)
        assert len(routes) == 1
        assert routes[0].ship_id == 7
        assert routes[0].tasks == ()


class TestListTradeRoutesMalformed:
    def test_task_missing_required_field_is_dropped(self) -> None:
        """From 無しの task は drop されるが route は維持．"""
        incomplete_task: list[Event] = [
            ("T", 1),
            ("A", 0x8006, struct.pack("<H", 200)),  # To のみ
            ("A", 0x8007, struct.pack("<i", 2143)),
            ("X",),
        ]
        inner = minimal_v3(
            tags=_TAGS,
            attribs=_ATTRIBS,
            events=_wrap_ca(
                [
                    _route(tasks=[], ship_id=1)
                    and [
                        ("T", 1),
                        ("T", 5),
                        *incomplete_task,
                        ("X",),
                        ("A", 0x8002, struct.pack("<i", 99)),
                        ("X",),
                    ],
                ]
            ),
        )
        routes = list_trade_routes(inner)
        assert len(routes) == 1
        assert routes[0].tasks == ()
        assert routes[0].ship_id == 99

    def test_truncated_attrib_values_ignored(self) -> None:
        """attrib content が型想定より短い場合は None 扱い (route も task も)．"""
        short_task: list[Event] = [
            ("T", 1),
            ("A", 0x8005, b"\x01"),  # From だが 1B しかない → None
            ("A", 0x8006, b"\x02"),  # To も同上
            ("A", 0x8007, b"\x03"),  # Product 1B → None
            ("A", 0x8008, b"\x04"),  # Balance 1B → None
            ("X",),
        ]
        route_events: list[Event] = [
            ("T", 1),
            ("T", 5),
            *short_task,
            ("X",),  # close TransportTasks
            ("A", 0x8001, b"\x01\x02"),  # Route 2B → None
            ("A", 0x8002, b"\x03"),  # ShipID 1B → None
            ("A", 0x8003, b"\x04\x05"),  # RoundTravel 2B → None
            ("A", 0x8004, b"\x06\x07"),  # EstablishTime 2B → None
            ("X",),
        ]
        inner = minimal_v3(
            tags=_TAGS,
            attribs=_ATTRIBS,
            events=_wrap_ca([route_events]),
        )
        routes = list_trade_routes(inner)
        assert len(routes) == 1
        assert routes[0] == TradeRouteDef(
            ship_id=None,
            route_hash=None,
            round_travel=None,
            establish_time=None,
            tasks=(),
        )

    def test_unknown_attribs_ignored(self) -> None:
        """route / task の認識外 attrib は単に無視される．"""
        # id=0x8009 ("id") は TransportType 用．route / task 直下に現れても無害．
        task_with_unknown: list[Event] = [
            ("T", 1),  # task
            ("A", 0x8005, struct.pack("<H", 1)),  # From
            ("A", 0x8006, struct.pack("<H", 2)),  # To
            ("A", 0x8007, struct.pack("<i", 3000)),  # Product
            ("A", 0x8009, b"\x00\x00"),  # unknown at task depth (tests final elif fallthrough)
            ("X",),
        ]
        route_events: list[Event] = [
            ("T", 1),
            ("T", 5),
            *task_with_unknown,
            ("X",),  # close TransportTasks
            ("A", 0x8009, b"\x00\x00"),  # unknown attrib at route depth
            ("A", 0x8002, struct.pack("<i", 123)),
            ("X",),
        ]
        inner = minimal_v3(
            tags=_TAGS,
            attribs=_ATTRIBS,
            events=_wrap_ca([route_events]),
        )
        routes = list_trade_routes(inner)
        assert routes[0].ship_id == 123
        assert routes[0].tasks[0].balance_raw == 0  # Balance 未指定 → default 0

    def test_root_level_terminator_handled(self) -> None:
        """minimal_v3 が末尾に吐く余剰 terminator で落ちない．"""
        inner = minimal_v3(
            tags=_TAGS,
            attribs=_ATTRIBS,
            events=_wrap_ca([_route(tasks=[], ship_id=1)]) + [("X",)],
        )
        routes = list_trade_routes(inner)
        assert len(routes) == 1
