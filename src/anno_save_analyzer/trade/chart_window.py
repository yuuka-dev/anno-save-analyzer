"""チャート描画の時間窓 (直近 N 分 / 全期間) を扱う純関数層．

書記長 feedback (v0.4.2 B): 長時間プレイ save では全履歴を 1 枚の chart に
詰めると直近の動きが見えない．``^R`` cycle で 120 分 / 4 時間 / 12 時間 /
24 時間 / 全期間を切り替える仕様．TUI 非依存にしておき，``TradeEvent`` 側も
``StorageTrend`` 側も同じ enum から filter できるようにする．
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

from .clock import TICKS_PER_MINUTE, latest_tick
from .models import TradeEvent


class ChartTimeWindow(Enum):
    """``^R`` で切替えるチャート時間窓．

    cycle 順は declaration 順と一致する．``ALL`` は ``max_minutes`` に ``None``
    を持ち，全期間表示を示す．他は分単位の上限．
    """

    LAST_120_MIN = ("last_120_min", 120.0)
    LAST_4H = ("last_4h", 240.0)
    LAST_12H = ("last_12h", 720.0)
    LAST_24H = ("last_24h", 1440.0)
    ALL = ("all", None)

    def __init__(self, locale_suffix: str, max_minutes: float | None) -> None:
        self.locale_suffix = locale_suffix
        self.max_minutes = max_minutes

    @property
    def locale_key(self) -> str:
        """chart タイトル suffix / Footer 表示に使う locale key．"""
        return f"chart.window.{self.locale_suffix}"

    def next(self) -> ChartTimeWindow:
        """cycle 次候補．末尾なら先頭へ戻る．"""
        members = list(ChartTimeWindow)
        return members[(members.index(self) + 1) % len(members)]


def filter_events[T: TradeEvent](events: Iterable[T], window: ChartTimeWindow) -> list[T]:
    """``timestamp_tick`` が window 内の event のみ残す．

    ``ALL`` や最新 tick が取れない場合 (全 event tick=None) は全量返す．
    ``timestamp_tick is None`` の event は常に除外 (chart プロット不能のため)．
    """
    tick_values = [ev.timestamp_tick for ev in events if ev.timestamp_tick is not None]
    now_tick = latest_tick(tick_values)
    if window.max_minutes is None or now_tick is None:
        return [ev for ev in events if ev.timestamp_tick is not None]
    cutoff = now_tick - window.max_minutes * TICKS_PER_MINUTE
    return [ev for ev in events if ev.timestamp_tick is not None and ev.timestamp_tick >= cutoff]


def filter_inventory_minutes(
    sample_minutes: list[float], window: ChartTimeWindow
) -> tuple[list[int], list[float]]:
    """inventory chart 用: sample_minutes (負数 / 0=最新) を window で切る．

    返り値は (keep_indices, kept_minutes)．sample 値本体は呼び出し側で
    ``indices`` を使って slice する (値と x 軸を同期させるため)．
    ``ALL`` は全量 (indices = range(len))．
    """
    if window.max_minutes is None:
        return list(range(len(sample_minutes))), list(sample_minutes)
    kept_idx: list[int] = []
    kept_min: list[float] = []
    for i, m in enumerate(sample_minutes):
        # sample_minutes は -(n-1)..0 で昇順．0 が最新 → window 内は -max_minutes 以上．
        if m >= -window.max_minutes:
            kept_idx.append(i)
            kept_min.append(m)
    return kept_idx, kept_min
