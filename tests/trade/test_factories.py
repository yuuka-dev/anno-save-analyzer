"""``trade.factories`` の単体テスト．

合成 FileDB で Factory7 walk を検証し，属性の有無 / 複数 AreaManager /
building_guid group 化などのコーナーを網羅する．
"""

from __future__ import annotations

import struct

import pytest

from anno_save_analyzer.trade.factories import (
    FactoryAggregate,
    FactoryInstance,
    ProductionStateSnapshot,
    list_factory_aggregates,
)
from tests.parser.filedb.conftest import Event, minimal_v3


def _f32_bytes(v: float) -> bytes:
    return struct.pack("<f", v)


def _i32_bytes(v: int) -> bytes:
    return struct.pack("<i", v)


# tag ID の慣例:
#   2 = AreaManager_<N>
#   3 = GameObject
#   4 = objects
#   1 = <1>  (anonymous)
#   5 = Factory7
#   6 = ProductionState
#   7 = (余り．別 AreaManager に使う)
# attrib ID:
#   0x8001 = guid
#   0x8002 = CurrentProductivity
#   0x8003 = InProgress
#   0x8004 = RemainingTime
#   0x8005 = Productivity
_TAGS = {
    2: "AreaManager_8706",
    3: "GameObject",
    4: "objects",
    5: "Factory7",
    6: "ProductionState",
}
_ATTRIBS = {
    0x8001: "guid",
    0x8002: "CurrentProductivity",
    0x8003: "InProgress",
    0x8004: "RemainingTime",
    0x8005: "Productivity",
}


def _build(
    factories: list[dict] | None = None,
    am_tag_name: str = "AreaManager_8706",
    *,
    include_am_wrapper: bool = True,
) -> bytes:
    """合成 FileDB 構築．各 factory は {guid, productivity, state?} の dict．

    ``state`` は ``{"in_progress": bool, "remaining_time": float,
    "cumulative": float}`` で欠けた key は attrib を出さない．None なら
    ProductionState タグ自体を省く．
    """
    factories = factories or []
    tags = dict(_TAGS)
    tags[2] = am_tag_name

    events: list[Event] = []
    if include_am_wrapper:
        events.append(("T", 2))  # AreaManager
        events.append(("T", 3))  # GameObject
        events.append(("T", 4))  # objects
    for f in factories:
        events.append(("T", 1))  # <1> object entry
        if f.get("guid") is not None:
            events.append(("A", 0x8001, _i32_bytes(f["guid"])))
        events.append(("T", 5))  # Factory7
        events.append(("A", 0x8002, _f32_bytes(f.get("productivity", 0.0))))
        state = f.get("state", ...)
        if state is not ... and state is not None:
            events.append(("T", 6))  # ProductionState
            if "in_progress" in state:
                events.append(("A", 0x8003, bytes([1 if state["in_progress"] else 0])))
            if "remaining_time" in state:
                events.append(("A", 0x8004, _f32_bytes(state["remaining_time"])))
            if "cumulative" in state:
                events.append(("A", 0x8005, _f32_bytes(state["cumulative"])))
            events.append(("X",))  # close ProductionState
        events.append(("X",))  # close Factory7
        events.append(("X",))  # close <1>
    if include_am_wrapper:
        events.append(("X",))  # close objects
        events.append(("X",))  # close GameObject
        events.append(("X",))  # close AreaManager
    return minimal_v3(tags=tags, attribs=_ATTRIBS, events=events)


# ---------- 基本 ----------


def test_empty_bytes_returns_empty() -> None:
    assert list_factory_aggregates(b"") == ()


def test_no_factory_returns_empty_instances() -> None:
    """AreaManager はあるが Factory7 が無いケース．aggregate は空 instances で返す．"""
    buf = _build(factories=[])
    out = list_factory_aggregates(buf)
    assert len(out) == 1
    assert out[0].area_manager == "AreaManager_8706"
    assert out[0].instances == ()
    assert out[0].total == 0
    assert out[0].mean_productivity == 0.0


def test_single_factory_with_state() -> None:
    buf = _build(
        factories=[
            {
                "guid": 1010278,  # Fish Coast Building (実サンプル GUID)
                "productivity": 0.75,
                "state": {"in_progress": True, "remaining_time": 12.5, "cumulative": 0.72},
            }
        ]
    )
    out = list_factory_aggregates(buf)
    assert len(out) == 1
    agg = out[0]
    assert agg.total == 1
    inst = agg.instances[0]
    assert inst.building_guid == 1010278
    assert inst.productivity == pytest.approx(0.75)
    assert inst.state is not None
    assert inst.state.in_progress is True
    assert inst.state.remaining_time == pytest.approx(12.5)
    assert inst.state.cumulative_productivity == pytest.approx(0.72)


def test_productivity_out_of_standard_range_preserved() -> None:
    """200% バフで productivity が 1.0 超えも落とさず保存する．"""
    buf = _build(factories=[{"guid": 1, "productivity": 1.8}])
    inst = list_factory_aggregates(buf)[0].instances[0]
    assert inst.productivity == pytest.approx(1.8)


def test_mean_productivity_simple_average() -> None:
    """mean は単純平均 (residents-weighted じゃない)．"""
    buf = _build(
        factories=[
            {"guid": 1, "productivity": 0.0},
            {"guid": 1, "productivity": 0.5},
            {"guid": 1, "productivity": 1.0},
        ]
    )
    agg = list_factory_aggregates(buf)[0]
    assert agg.total == 3
    assert agg.mean_productivity == pytest.approx(0.5)


def test_factory_without_production_state() -> None:
    """ProductionState 子タグ自体が無いケース．state=None になる．"""
    buf = _build(factories=[{"guid": 42, "productivity": 1.0, "state": None}])
    inst = list_factory_aggregates(buf)[0].instances[0]
    assert inst.state is None


def test_factory_without_guid_skipped() -> None:
    """guid attrib が無い object entry の Factory7 は落とす (建物特定不能)．"""
    buf = _build(factories=[{"guid": None, "productivity": 0.5}])
    assert list_factory_aggregates(buf)[0].instances == ()


# ---------- 複数 AreaManager ----------


def test_multiple_area_managers_separate_aggregates() -> None:
    """2 つの AreaManager それぞれで instances が独立に溜まる．"""
    buf1 = _build(
        am_tag_name="AreaManager_100",
        factories=[{"guid": 1, "productivity": 0.5}],
    )
    buf2 = _build(
        am_tag_name="AreaManager_200",
        factories=[{"guid": 2, "productivity": 1.0}],
    )
    # 2 つを連結できないので，tags を共有する合成を作り直す
    tags = dict(_TAGS)
    tags[2] = "AreaManager_100"
    tags[7] = "AreaManager_200"
    events: list[Event] = [
        ("T", 2),
        ("T", 3),
        ("T", 4),
        ("T", 1),
        ("A", 0x8001, _i32_bytes(1)),
        ("T", 5),
        ("A", 0x8002, _f32_bytes(0.5)),
        ("X",),
        ("X",),
        ("X",),
        ("X",),
        ("X",),
        ("T", 7),
        ("T", 3),
        ("T", 4),
        ("T", 1),
        ("A", 0x8001, _i32_bytes(2)),
        ("T", 5),
        ("A", 0x8002, _f32_bytes(1.0)),
        ("X",),
        ("X",),
        ("X",),
        ("X",),
        ("X",),
    ]
    del buf1, buf2
    buf = minimal_v3(tags=tags, attribs=_ATTRIBS, events=events)
    out = list_factory_aggregates(buf)
    by_name = {a.area_manager: a for a in out}
    assert set(by_name) == {"AreaManager_100", "AreaManager_200"}
    assert by_name["AreaManager_100"].instances[0].building_guid == 1
    assert by_name["AreaManager_200"].instances[0].building_guid == 2


def test_by_building_groups_instances() -> None:
    buf = _build(
        factories=[
            {"guid": 100, "productivity": 0.5},
            {"guid": 100, "productivity": 1.0},
            {"guid": 200, "productivity": 0.8},
        ]
    )
    agg = list_factory_aggregates(buf)[0]
    grouped = agg.by_building()
    assert set(grouped) == {100, 200}
    assert len(grouped[100]) == 2
    assert len(grouped[200]) == 1


# ---------- Pydantic model properties ----------


def test_aggregate_model_is_frozen() -> None:
    agg = FactoryAggregate(area_manager="X", instances=())
    with pytest.raises(Exception):  # noqa: B017
        agg.area_manager = "Y"  # type: ignore[misc]


def test_production_state_snapshot_frozen() -> None:
    s = ProductionStateSnapshot(in_progress=True)
    with pytest.raises(Exception):  # noqa: B017
        s.in_progress = False  # type: ignore[misc]


def test_instance_model_is_frozen() -> None:
    i = FactoryInstance(building_guid=1, productivity=0.5)
    with pytest.raises(Exception):  # noqa: B017
        i.productivity = 1.0  # type: ignore[misc]
