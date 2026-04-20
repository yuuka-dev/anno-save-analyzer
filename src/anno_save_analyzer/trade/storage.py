"""島ごとの在庫時系列 (StorageTrends) 抽出．

Anno 117 の内側 Session DOM には ``AreaInfo > <1> > AreaEconomy >
StorageTrends`` 階層で **物資ごとの 120 サンプル固定 ring buffer** が保存されて
いる．本モジュールは

1. 生 FileDB bytes から ``IslandStorageTrend`` Pydantic model を抽出
2. ``latest`` / ``peak`` / ``mean`` / ``slope`` 等の derived プロパティを提供

の 2 段階を担う．TUI の Inventory tab / CLI の ``trade inventory`` 将来実装で
消費される．

## DOM 構造 (実測)

```
AreaInfo > <1> (player island, CityName を持つ)
    └─ AreaEconomy
        └─ StorageTrends
            └─ <ProductGUID> (anonymous attrib, i32)
                └─ <1>
                    ├─ A LastPointTime: i64 (最新サンプル tick)
                    ├─ A Estimation: i32
                    └─ T Points
                        ├─ A capacity: i64 (120 固定)
                        ├─ A size: i64 (120 固定)
                        └─ A <32768> × 120 (i32 各サンプル値．ring buffer)
```

書記長の sample_anno117.a8s で 13 player islands × 110 unique GUIDs = 1,430
trend rows を検証済．``Points`` は shift register で ``[-1]`` = 最新サンプル．
"""

from __future__ import annotations

import struct
from collections.abc import Iterable, Iterator

from pydantic import BaseModel, Field, computed_field

from anno_save_analyzer.parser.filedb import (
    EventKind,
    TagSection,
    detect_version,
    iter_dom,
    parse_tag_section,
)

_AREA_INFO_TAG = "AreaInfo"
_AREA_ECONOMY_TAG = "AreaEconomy"
_STORAGE_TRENDS_TAG = "StorageTrends"
_POINTS_TAG = "Points"
_CITY_NAME_ATTRIB = "CityName"
_LAST_POINT_TIME_ATTRIB = "LastPointTime"


class PointSeries(BaseModel):
    """StorageTrends 配下の ``Points`` 時系列．

    ``samples`` は shift register で古い方が先頭．``samples[-1]`` が最新．
    実セーブでは ``capacity == size == 120`` 固定．
    """

    capacity: int
    size: int
    samples: tuple[int, ...]

    model_config = {"frozen": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def latest(self) -> int:
        """最新サンプル (= ``samples[-1]``)．空ならば 0．"""
        return self.samples[-1] if self.samples else 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def peak(self) -> int:
        """観測された最大値．"""
        return max(self.samples) if self.samples else 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mean(self) -> float:
        """算術平均．空なら 0．"""
        return sum(self.samples) / len(self.samples) if self.samples else 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def slope(self) -> float:
        """線形回帰の傾き．増減トレンドの符号判定に使う．

        単純な最小二乗で y = a*x + b の ``a`` を返す．サンプル数 < 2 なら 0．
        """
        n = len(self.samples)
        if n < 2:
            return 0.0
        # x = 0, 1, ..., n-1
        sum_x = n * (n - 1) / 2
        sum_y = sum(self.samples)
        sum_xy = sum(i * y for i, y in enumerate(self.samples))
        sum_xx = sum(i * i for i in range(n))
        denom = n * sum_xx - sum_x * sum_x
        if denom == 0:
            return 0.0
        return (n * sum_xy - sum_x * sum_y) / denom


class IslandStorageTrend(BaseModel):
    """1 島 × 1 物資の在庫時系列レコード．"""

    island_name: str
    product_guid: int
    last_point_tick: int | None = Field(default=None, description="最新サンプル時点のゲーム内 tick")
    estimation: int | None = Field(default=None, description="StorageTrends 内部フラグ．詳細未解明")
    points: PointSeries

    model_config = {"frozen": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def latest(self) -> int:
        return self.points.latest

    @computed_field  # type: ignore[prop-decorator]
    @property
    def peak(self) -> int:
        return self.points.peak


def list_storage_trends(inner_session: bytes) -> tuple[IslandStorageTrend, ...]:
    """内側 Session FileDB から島 × 物資の時系列を全件抽出．

    プレイヤー保有島 (``AreaInfo > <1>`` 直下に ``CityName`` attrib を持つもの)
    のみ対象．NPC 島の StorageTrends は CityName ゲートで除外．
    """
    if not inner_session:
        return ()
    version = detect_version(inner_session)
    section = parse_tag_section(inner_session, version)
    return tuple(_iter_trends(inner_session, version, section))


def _iter_trends(inner: bytes, version, section: TagSection) -> Iterator[IslandStorageTrend]:
    tag_ids = _resolve_tag_ids(section)
    if tag_ids is None:
        return
    area_info_id, area_economy_id, storage_trends_id, points_id = tag_ids

    stack: list[int] = []
    in_area_info_depth: int | None = None
    entry_depth: int | None = None
    city_name: str | None = None
    in_area_economy_depth: int | None = None
    in_storage_trends_depth: int | None = None
    current_guid: int | None = None
    in_trend_entry_depth: int | None = None
    current_last_point: int | None = None
    current_estimation: int | None = None
    in_points_depth: int | None = None
    current_points_capacity: int | None = None
    current_points_size: int | None = None
    current_samples: list[int] = []

    for ev in iter_dom(inner, version, tag_section=section):
        if ev.kind is EventKind.TAG:
            stack.append(ev.id_)
            depth = len(stack)
            if ev.id_ == area_info_id and in_area_info_depth is None:
                in_area_info_depth = depth
            elif (
                in_area_info_depth is not None
                and entry_depth is None
                and depth == in_area_info_depth + 1
            ):
                entry_depth = depth
                city_name = None
            elif (
                ev.id_ == area_economy_id
                and entry_depth is not None
                and in_area_economy_depth is None
            ):
                in_area_economy_depth = depth
            elif (
                ev.id_ == storage_trends_id
                and in_area_economy_depth is not None
                and in_storage_trends_depth is None
            ):
                in_storage_trends_depth = depth
            elif (
                in_storage_trends_depth is not None
                and in_trend_entry_depth is None
                and depth == in_storage_trends_depth + 1
            ):
                # StorageTrends > <1> (trend entry)．ProductGUID はこの entry の
                # 兄弟位置にある anonymous attrib (stack 上は StorageTrends 直下)
                # に載り，walk の ATTRIB 分岐で ``current_guid`` に記録する．
                in_trend_entry_depth = depth
                current_last_point = None
                current_estimation = None
                current_points_capacity = None
                current_points_size = None
                current_samples = []
            elif (
                ev.id_ == points_id and in_trend_entry_depth is not None and in_points_depth is None
            ):
                in_points_depth = depth
            continue

        if ev.kind is EventKind.ATTRIB:
            if (
                entry_depth is not None
                and len(stack) == entry_depth
                and ev.name == _CITY_NAME_ATTRIB
            ):
                city_name = (
                    ev.content.decode("utf-16-le", errors="replace")
                    .rstrip("\x00")
                    .replace("\u200b", "")
                    .strip()
                )
            elif (
                in_storage_trends_depth is not None
                and len(stack) == in_storage_trends_depth
                and ev.name is None
                and len(ev.content) == 4
            ):
                # StorageTrends 直下の anonymous i32 attrib = ProductGUID
                current_guid = struct.unpack_from("<i", ev.content, 0)[0]
            elif in_trend_entry_depth is not None and len(stack) == in_trend_entry_depth:
                if ev.name == _LAST_POINT_TIME_ATTRIB and len(ev.content) >= 8:
                    current_last_point = struct.unpack_from("<q", ev.content, 0)[0]
                elif ev.name == "Estimation" and len(ev.content) >= 4:
                    current_estimation = struct.unpack_from("<i", ev.content, 0)[0]
            elif in_points_depth is not None and len(stack) == in_points_depth:
                if ev.name == "capacity" and len(ev.content) >= 8:
                    current_points_capacity = struct.unpack_from("<q", ev.content, 0)[0]
                elif ev.name == "size" and len(ev.content) >= 8:
                    current_points_size = struct.unpack_from("<q", ev.content, 0)[0]
                elif ev.name is None and len(ev.content) == 4:
                    current_samples.append(struct.unpack_from("<i", ev.content, 0)[0])
            continue

        if not stack:
            continue
        closing_depth = len(stack)
        if in_points_depth is not None and closing_depth == in_points_depth:
            in_points_depth = None
        if in_trend_entry_depth is not None and closing_depth == in_trend_entry_depth:
            # trend entry close: プレイヤー島 (city_name) かつ GUID 既知なら yield
            if (
                city_name
                and current_guid is not None
                and current_points_capacity is not None
                and current_points_size is not None
            ):
                yield IslandStorageTrend(
                    island_name=city_name,
                    product_guid=current_guid,
                    last_point_tick=current_last_point,
                    estimation=current_estimation,
                    points=PointSeries(
                        capacity=current_points_capacity,
                        size=current_points_size,
                        samples=tuple(current_samples),
                    ),
                )
            in_trend_entry_depth = None
        if in_storage_trends_depth is not None and closing_depth == in_storage_trends_depth:
            in_storage_trends_depth = None
            current_guid = None
        if in_area_economy_depth is not None and closing_depth == in_area_economy_depth:
            in_area_economy_depth = None
        if entry_depth is not None and closing_depth == entry_depth:
            entry_depth = None
            city_name = None
        if in_area_info_depth is not None and closing_depth == in_area_info_depth:
            in_area_info_depth = None
        stack.pop()


def _resolve_tag_ids(section: TagSection) -> tuple[int, int, int, int] | None:
    """必要な 4 タグ (AreaInfo / AreaEconomy / StorageTrends / Points) を辞書から解決．"""
    required = {
        _AREA_INFO_TAG: None,
        _AREA_ECONOMY_TAG: None,
        _STORAGE_TRENDS_TAG: None,
        _POINTS_TAG: None,
    }
    for tid, name in section.tags.entries.items():
        if name in required:
            required[name] = tid
    if any(v is None for v in required.values()):
        return None
    return (
        required[_AREA_INFO_TAG],
        required[_AREA_ECONOMY_TAG],
        required[_STORAGE_TRENDS_TAG],
        required[_POINTS_TAG],
    )


def group_by_island(
    trends: Iterable[IslandStorageTrend],
) -> dict[str, tuple[IslandStorageTrend, ...]]:
    """island_name をキーに pivot．Inventory tab の island > product hierarchy 用．"""
    out: dict[str, list[IslandStorageTrend]] = {}
    for t in trends:
        out.setdefault(t.island_name, []).append(t)
    return {name: tuple(items) for name, items in out.items()}
