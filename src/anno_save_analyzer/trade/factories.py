"""島ごとの Factory7 抽出 (v0.4 supply-balance の供給側データ)．

Factory7 を持つ建物ノードを対象に，この docstring で定義する DOM 前提を
state machine で走査する．

## DOM 構造 (Anno 1800 / 117 共通)

```
AreaManager_<N>
└─ GameObject
    └─ objects
        └─ <1>                       (1 建物インスタンス)
            ├─ A guid                i32  ← 建物 GUID (buildings.yaml key)
            ├─ A ID / Position / ... (他メタ)
            └─ Factory7              (このタグを持つ建物のみ生産コンポ)
                ├─ A CurrentProductivity f32 (通常 0.0–2.0 / DLC 系アイテムで 3.0+ 実測)
                └─ ProductionState
                    ├─ A InProgress       u8 bool
                    ├─ A RemainingTime    f32 (game tick)
                    └─ A Productivity     f32 (累積，履歴用)
```

``Pausable`` / ``Maintenance`` 等の兄弟タグは本 module では扱わない．停止状態
や維持費は future work (``balance.py`` 合流時).
"""

from __future__ import annotations

import struct
from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import BaseModel, Field, computed_field

from anno_save_analyzer.parser.filedb import (
    EventKind,
    TagSection,
    detect_version,
    iter_dom,
    parse_tag_section,
)

_AREA_MANAGER_PREFIX = "AreaManager_"
_OBJECTS = "objects"
_FACTORY7 = "Factory7"
_PRODUCTION_STATE = "ProductionState"
_CURRENT_PRODUCTIVITY = "CurrentProductivity"
_IN_PROGRESS = "InProgress"
_REMAINING_TIME = "RemainingTime"
_PRODUCTIVITY = "Productivity"
_GUID_ATTRIB = "guid"


def _f32(buf: bytes) -> float:
    return struct.unpack_from("<f", buf, 0)[0] if len(buf) >= 4 else 0.0


def _i32(buf: bytes) -> int:
    return struct.unpack_from("<i", buf, 0)[0] if len(buf) >= 4 else 0


class ProductionStateSnapshot(BaseModel):
    """``ProductionState`` 子タグのスナップショット．全属性 optional．"""

    in_progress: bool | None = None
    """``True`` で生産中 (enabled かつ原料充足)，``False`` で停止．"""
    remaining_time: float | None = None
    """次サイクル完了までの残秒 (game tick 単位)．"""
    cumulative_productivity: float | None = None
    """``ProductionState > Productivity``．累積生産レートの移動平均 (履歴用)．"""

    model_config = {"frozen": True}


class FactoryInstance(BaseModel):
    """1 工場インスタンス．``guid`` attrib 経由で建物種別が引ける．"""

    building_guid: int
    """``objects > <1>`` 直下の ``guid`` attrib．``buildings.yaml`` の key に対応．"""
    productivity: float
    """``Factory7 > CurrentProductivity``．通常 0.0–2.0 (200% バフ込み) だが
    DLC のアイテムスタッキングで 3.0 以上になるケースも実在する (書記長 save
    で 300% 実測)．UI 側で ``* 100`` して % 表示する想定．"""
    state: ProductionStateSnapshot | None = None
    """``ProductionState`` の内容．全属性欠けてれば ``None``．"""

    model_config = {"frozen": True}


class FactoryAggregate(BaseModel):
    """1 AreaManager あたりの工場群．"""

    area_manager: str = Field(..., description="AreaManager_<N> タグ名")
    instances: tuple[FactoryInstance, ...] = Field(default_factory=tuple)

    model_config = {"frozen": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total(self) -> int:
        return len(self.instances)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mean_productivity(self) -> float:
        """全工場の productivity 単純平均．0 工場なら 0.0．"""
        if not self.instances:
            return 0.0
        return sum(i.productivity for i in self.instances) / len(self.instances)

    def by_building(self) -> dict[int, tuple[FactoryInstance, ...]]:
        """building_guid で group 化して返す．"""
        grouped: dict[int, list[FactoryInstance]] = {}
        for inst in self.instances:
            grouped.setdefault(inst.building_guid, []).append(inst)
        return {k: tuple(v) for k, v in grouped.items()}


def list_factory_aggregates(inner_session: bytes) -> tuple[FactoryAggregate, ...]:
    """inner session (per-session FileDB) から AreaManager 単位の工場集計を返す．

    プレイヤー島 / NPC 島を区別せずに全 AreaManager を返す．プレイヤー絞り込み
    は ``parser.filedb.session.list_player_islands`` の city_name 結合で上位層に委譲．
    """
    if not inner_session:
        return ()
    version = detect_version(inner_session)
    section = parse_tag_section(inner_session, version)
    return tuple(_walk(inner_session, version, section))


def _walk(inner: bytes, version, section: TagSection) -> Iterable[FactoryAggregate]:
    """DOM ストリームを state machine で舐めて FactoryAggregate を yield する．"""
    stack: list[str] = []
    in_am: tuple[int, str] | None = None  # (depth, name)
    accums: dict[str, list[FactoryInstance]] = {}

    in_obj_entry: int | None = None  # depth of objects > <1>
    obj_guid: int | None = None

    in_f7: int | None = None  # depth of Factory7
    cur_productivity = 0.0
    in_ps: int | None = None  # depth of ProductionState
    ps_accum = _PSAccum()

    for ev in iter_dom(inner, version, tag_section=section):
        if ev.kind is EventKind.TAG:
            name = ev.name or f"<{ev.id_}>"
            stack.append(name)
            depth = len(stack)
            if name.startswith(_AREA_MANAGER_PREFIX) and in_am is None:
                in_am = (depth, name)
                accums.setdefault(name, [])
            elif (
                in_am is not None
                and in_obj_entry is None
                and name == "<1>"
                and len(stack) >= 2
                and stack[-2] == _OBJECTS
            ):
                in_obj_entry = depth
                obj_guid = None
            elif in_obj_entry is not None and in_f7 is None and name == _FACTORY7:
                in_f7 = depth
                cur_productivity = 0.0
                ps_accum = _PSAccum()
            elif (
                in_f7 is not None
                and in_ps is None
                and name == _PRODUCTION_STATE
                and depth == in_f7 + 1
            ):
                in_ps = depth
            continue

        if ev.kind is EventKind.ATTRIB:
            if in_obj_entry is not None and len(stack) == in_obj_entry and ev.name == _GUID_ATTRIB:
                obj_guid = _i32(ev.content)
            elif in_f7 is not None and len(stack) == in_f7 and ev.name == _CURRENT_PRODUCTIVITY:
                cur_productivity = _f32(ev.content)
            elif in_ps is not None and len(stack) == in_ps:
                if ev.name == _IN_PROGRESS:
                    ps_accum.in_progress = bool(ev.content and ev.content[0])
                elif ev.name == _REMAINING_TIME:
                    ps_accum.remaining_time = _f32(ev.content)
                elif ev.name == _PRODUCTIVITY:
                    ps_accum.cumulative = _f32(ev.content)
            continue

        # Terminator
        if not stack:
            continue
        closing_depth = len(stack)
        if in_ps is not None and closing_depth == in_ps:
            in_ps = None
        if in_f7 is not None and closing_depth == in_f7:
            # Factory7 close: commit instance
            if in_am is not None and obj_guid is not None:
                accums[in_am[1]].append(
                    FactoryInstance(
                        building_guid=obj_guid,
                        productivity=cur_productivity,
                        state=ps_accum.freeze(),
                    )
                )
            in_f7 = None
        if in_obj_entry is not None and closing_depth == in_obj_entry:
            in_obj_entry = None
            obj_guid = None
        if in_am is not None and closing_depth == in_am[0]:
            in_am = None
        stack.pop()

    for am_name, instances in accums.items():
        yield FactoryAggregate(area_manager=am_name, instances=tuple(instances))


@dataclass
class _PSAccum:
    """ProductionState 属性を組み立てるための可変バッファ．"""

    in_progress: bool | None = None
    remaining_time: float | None = None
    cumulative: float | None = None

    def freeze(self) -> ProductionStateSnapshot | None:
        if self.in_progress is None and self.remaining_time is None and self.cumulative is None:
            return None
        return ProductionStateSnapshot(
            in_progress=self.in_progress,
            remaining_time=self.remaining_time,
            cumulative_productivity=self.cumulative,
        )
