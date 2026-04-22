"""trade.storage の単体テスト．

合成 FileDB fixture で StorageTrends の walk / Pydantic モデル構築 / derived
properties を verify する．``AreaInfo > <1> > AreaEconomy > StorageTrends >
<1> > Points > <32768>×N`` の最小 DOM を組み立てる．
"""

from __future__ import annotations

import struct

from anno_save_analyzer.trade.storage import (
    IslandStorageTrend,
    PointSeries,
    group_by_island,
    list_storage_trends,
)
from tests.parser.filedb.conftest import Event, minimal_v3


def _trend_entry(
    *,
    product_guid: int,
    samples: list[int],
    last_point_tick: int | None = 144380000,
    estimation: int | None = 0,
    capacity: int | None = 120,
    size: int | None = 120,
) -> list[Event]:
    """StorageTrends 直下の (anon attrib + <1>) ペアを組む．

    ``capacity`` / ``size`` が ``None`` の場合は named attrib を省く．
    Anno 1800 の 2 サンプル形式を再現する用途．
    """
    out: list[Event] = [
        ("A", 0x8FFF, struct.pack("<i", product_guid)),  # anonymous ProductGUID
        ("T", 1),  # trend entry <1>
    ]
    if last_point_tick is not None:
        out.append(("A", 0x8001, struct.pack("<q", last_point_tick)))  # LastPointTime
    if estimation is not None:
        out.append(("A", 0x8002, struct.pack("<i", estimation)))
    out.append(("T", 2))  # Points
    if capacity is not None:
        out.append(("A", 0x8003, struct.pack("<q", capacity)))
    if size is not None:
        out.append(("A", 0x8004, struct.pack("<q", size)))
    for v in samples:
        out.append(("A", 0x8FFF, struct.pack("<i", v)))  # anonymous sample
    out.append(("X",))  # close Points
    out.append(("X",))  # close <1>
    return out


def _build_storage_fixture(
    *,
    islands: list[tuple[str | None, list[tuple[int, list[int]]]]],
) -> bytes:
    """``islands`` = ``[(city_name_or_None, [(guid, samples)...]), ...]``．

    ``city_name=None`` の island は CityName attrib なしで NPC 扱いとなり，
    StorageTrends は出しても walk で弾かれる想定．
    """
    tags = {
        1: "Anonymous",  # 匿名 <1> 用のダミー (id=1 は登録しなくても OK)
        2: "Points",
        3: "StorageTrends",
        4: "AreaEconomy",
        5: "AreaInfo",
    }
    # id=1 は辞書登録しない (anonymous <1>)．tags から除外．
    tags = {k: v for k, v in tags.items() if k != 1}
    attribs = {
        0x8001: "LastPointTime",
        0x8002: "Estimation",
        0x8003: "capacity",
        0x8004: "size",
        0x8005: "CityName",
        # 0x8FFF は登録しない (anonymous)．ただし minimal_v3 は登録必須かも…
        # 実際 minimal_v3 の attribs は dict で任意 id OK．anon 用として登録せず運用．
    }

    events: list[Event] = [("T", 5)]  # AreaInfo
    for city_name, trends in islands:
        events.append(("T", 1))  # AreaInfo > <1>
        if city_name is not None:
            events.append(("A", 0x8005, city_name.encode("utf-16-le")))
        events.append(("T", 4))  # AreaEconomy
        events.append(("T", 3))  # StorageTrends
        for guid, samples in trends:
            events.extend(_trend_entry(product_guid=guid, samples=samples))
        events.append(("X",))  # close StorageTrends
        events.append(("X",))  # close AreaEconomy
        events.append(("X",))  # close AreaInfo > <1>
    events.append(("X",))  # close AreaInfo
    return minimal_v3(tags=tags, attribs=attribs, events=events)


class TestListStorageTrendsHappy:
    def test_extracts_trends_for_player_island(self) -> None:
        inner = _build_storage_fixture(
            islands=[
                ("大阪民国", [(2063, [1, 2, 3, 4, 5]), (2088, [10, 20, 30])]),
            ],
        )
        trends = list_storage_trends(inner)
        assert len(trends) == 2
        names = {t.island_name for t in trends}
        assert names == {"大阪民国"}
        guids = {t.product_guid for t in trends}
        assert guids == {2063, 2088}

    def test_last_point_tick_captured(self) -> None:
        inner = _build_storage_fixture(
            islands=[("x", [(100, [1, 2])])],
        )
        trends = list_storage_trends(inner)
        assert trends[0].last_point_tick == 144380000

    def test_estimation_captured(self) -> None:
        inner = _build_storage_fixture(islands=[("x", [(100, [1])])])
        trends = list_storage_trends(inner)
        assert trends[0].estimation == 0

    def test_multiple_islands(self) -> None:
        inner = _build_storage_fixture(
            islands=[
                ("大阪民国", [(2063, [5])]),
                ("ジョウト地方", [(2069, [10])]),
            ],
        )
        trends = list_storage_trends(inner)
        assert {t.island_name for t in trends} == {"大阪民国", "ジョウト地方"}


class TestNpcIslandFilter:
    def test_city_name_absent_island_is_skipped(self) -> None:
        """NPC 島 (CityName 無し) の StorageTrends は yield されない．"""
        inner = _build_storage_fixture(
            islands=[
                ("大阪民国", [(2063, [1])]),
                (None, [(2063, [1])]),  # NPC 島．CityName なし
            ],
        )
        trends = list_storage_trends(inner)
        assert len(trends) == 1
        assert trends[0].island_name == "大阪民国"


class TestAnno1800Schema:
    """Anno 1800 は Points に capacity/size named attrib を持たず anonymous
    i32 × 2 だけを残す schema．``len(samples)`` でフォールバックして yield
    される必要がある (117 の full time-series と統一 API)．
    """

    def test_yields_trend_when_capacity_size_missing(self) -> None:
        """capacity/size 欠落でも samples があれば trend を yield．"""
        inner = _build_storage_fixture(
            islands=[
                # Anno 1800 の実形式: 2 サンプルだけ + capacity/size 省略
                (
                    "レニングラード",
                    [
                        (1010566, [186, 185]),  # delta: 1 減った
                        (535, [23, 2]),  # Local Mail 大量消費直後
                    ],
                ),
            ],
        )
        # _trend_entry デフォルトを Anno 1800 形式にオーバーライド
        tags = {2: "Points", 3: "StorageTrends", 4: "AreaEconomy", 5: "AreaInfo"}
        attribs = {0x8001: "LastPointTime", 0x8002: "Estimation", 0x8005: "CityName"}
        events: list[Event] = [
            ("T", 5),
            ("T", 1),  # AreaInfo > <1>
            ("A", 0x8005, "レニングラード".encode("utf-16-le")),
            ("T", 4),
            ("T", 3),
            *_trend_entry(product_guid=1010566, samples=[186, 185], capacity=None, size=None),
            *_trend_entry(product_guid=535, samples=[23, 2], capacity=None, size=None),
            ("X",),
            ("X",),
            ("X",),
            ("X",),
        ]
        inner = minimal_v3(tags=tags, attribs=attribs, events=events)
        trends = list_storage_trends(inner)
        assert len(trends) == 2
        t0 = next(t for t in trends if t.product_guid == 1010566)
        assert t0.points.samples == (186, 185)
        # capacity/size は len(samples) にフォールバック
        assert t0.points.capacity == 2
        assert t0.points.size == 2
        # latest は最新サンプル = samples[-1] = 185
        assert t0.latest == 185
        assert t0.peak == 186
        # 2 点 slope: (n*sum_xy - sum_x*sum_y) / (n*sum_xx - sum_x^2)
        # = (2*185 - 1*(186+185)) / (2*1 - 1) = (370-371)/1 = -1
        assert t0.points.slope == -1.0

    def test_empty_samples_still_rejected(self) -> None:
        """samples 0 個 (なにも attrib 入っとらん Points) は yield されない．
        fallback 条件 ``current_samples`` truthy check で弾かれる．"""
        tags = {2: "Points", 3: "StorageTrends", 4: "AreaEconomy", 5: "AreaInfo"}
        attribs = {0x8005: "CityName"}
        events: list[Event] = [
            ("T", 5),
            ("T", 1),
            ("A", 0x8005, "X".encode("utf-16-le")),
            ("T", 4),
            ("T", 3),
            ("A", 0x8FFF, struct.pack("<i", 42)),  # ProductGUID anon
            ("T", 1),  # trend entry <1>
            ("T", 2),  # Points (empty)
            ("X",),
            ("X",),
            ("X",),  # StorageTrends
            ("X",),  # AreaEconomy
            ("X",),  # AreaInfo > <1>
            ("X",),  # AreaInfo
        ]
        inner = minimal_v3(tags=tags, attribs=attribs, events=events)
        assert list_storage_trends(inner) == ()


class TestEdgeCases:
    def test_empty_bytes_returns_empty(self) -> None:
        assert list_storage_trends(b"") == ()

    def test_missing_tags_returns_empty(self) -> None:
        """辞書に ``AreaInfo`` 等 4 タグ揃ってなければ (a7s でない等) 空返却．"""
        inner = minimal_v3(tags={2: "Other"}, attribs={}, events=[("T", 2), ("X",)])
        assert list_storage_trends(inner) == ()

    def test_city_name_strips_zero_width_space(self) -> None:
        """``\\u200b スターリングラード`` のように先頭 ZWSP が混ざっても strip される．"""
        inner = _build_storage_fixture(
            islands=[("\u200bスターリングラード", [(100, [1])])],
        )
        trends = list_storage_trends(inner)
        assert trends[0].island_name == "スターリングラード"


class TestPointSeriesDerived:
    def test_latest_and_peak(self) -> None:
        ps = PointSeries(capacity=5, size=5, samples=(1, 3, 2, 5, 4))
        assert ps.latest == 4
        assert ps.peak == 5

    def test_mean(self) -> None:
        ps = PointSeries(capacity=3, size=3, samples=(1, 2, 3))
        assert ps.mean == 2.0

    def test_slope_positive_trend(self) -> None:
        ps = PointSeries(capacity=3, size=3, samples=(1, 2, 3))
        assert ps.slope > 0

    def test_slope_zero_for_flat(self) -> None:
        ps = PointSeries(capacity=3, size=3, samples=(5, 5, 5))
        assert ps.slope == 0.0

    def test_slope_single_sample_is_zero(self) -> None:
        ps = PointSeries(capacity=1, size=1, samples=(42,))
        assert ps.slope == 0.0

    def test_empty_samples_safe(self) -> None:
        ps = PointSeries(capacity=0, size=0, samples=())
        assert ps.latest == 0
        assert ps.peak == 0
        assert ps.mean == 0.0
        assert ps.slope == 0.0


class TestIslandStorageTrendDerived:
    def test_computed_latest_peak_proxies_to_points(self) -> None:
        t = IslandStorageTrend(
            island_name="x",
            product_guid=1,
            points=PointSeries(capacity=3, size=3, samples=(1, 2, 5)),
        )
        assert t.latest == 5
        assert t.peak == 5


class TestGroupByIsland:
    def test_groups_by_island_name(self) -> None:
        trends = [
            IslandStorageTrend(
                island_name="A",
                product_guid=1,
                points=PointSeries(capacity=1, size=1, samples=(1,)),
            ),
            IslandStorageTrend(
                island_name="B",
                product_guid=1,
                points=PointSeries(capacity=1, size=1, samples=(2,)),
            ),
            IslandStorageTrend(
                island_name="A",
                product_guid=2,
                points=PointSeries(capacity=1, size=1, samples=(3,)),
            ),
        ]
        out = group_by_island(trends)
        assert set(out) == {"A", "B"}
        assert len(out["A"]) == 2
        assert len(out["B"]) == 1

    def test_empty_input(self) -> None:
        assert group_by_island([]) == {}
