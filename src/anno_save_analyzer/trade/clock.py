"""ゲーム内 tick ↔ 実時間 (分) 換算．

Anno 1800 / 117 の内部 tick はシミュレーション歩進単位で，実測上 1 tick ≈ 100 ms
(= 600 ticks/分)．実セーブで ``LastPointTime`` や ``ExecutionTime`` の差分と
サンプル数から逆算しても 600 付近で一致する．

将来別タイトル / パッチで tick 速度が変わる場合に備えて定数で隔離する．
"""

from __future__ import annotations

from collections.abc import Iterable

# 1 分あたりの tick 数．書記長の sample_anno117.a8s で LastPointTime の
# 差分分布から検証した値．Anno 1800 も同等と仮定 (要検証)．
TICKS_PER_MINUTE = 600

# ``StorageTrends > Points`` の 1 サンプル = 何 tick か．暫定値 = 1 分 (600)．
# 公式ドキュメントは無く，Anno 内部の「在庫推移グラフ」の UI 観察とサンプル数
# (capacity=120 固定) から 「120 samples = 2 hours」 と仮置きしている．書記長の
# dogfood で違和感があれば調整する．clock モジュールに隔離して ad-hoc 値を
# コード上からも見分けやすくする．
SAMPLE_INTERVAL_TICKS = TICKS_PER_MINUTE  # 1 sample = 1 minute 仮定


def minutes_relative_to(tick: int, *, now_tick: int) -> float:
    """``tick`` を ``now_tick`` からの相対分数 (負=過去) として返す．

    chart の x 軸に使う: 最新イベント = 0 / 過去ほど負の値．
    """
    return (tick - now_tick) / TICKS_PER_MINUTE


def latest_tick(ticks: Iterable[int]) -> int | None:
    """非空なら最大 tick，空なら ``None``．"""
    values = list(ticks)
    return max(values) if values else None


# spread がこの分数を超えたら時間単位に切り替える閾値．
_HOURS_UNIT_THRESHOLD_MIN = 120.0


def inventory_sample_minutes(
    n_samples: int, step_ticks: int = SAMPLE_INTERVAL_TICKS
) -> list[float]:
    """StorageTrends の N サンプルを「何分前」相対値に展開．

    最新サンプル (``samples[-1]``) を 0，最古を ``-(n-1) * step / ticks_per_min``
    として左に並べる．chart の x 軸は昇順なので最古が左端．
    """
    return [(i - (n_samples - 1)) * step_ticks / TICKS_PER_MINUTE for i in range(n_samples)]


def pick_time_unit(values_minutes: Iterable[float]) -> tuple[str, float]:
    """spread に応じて「分」/「時間」を選び，``(unit_key, divisor)`` を返す．

    ``unit_key`` は locale key の suffix ("minutes_ago" / "hours_ago") で，
    ``divisor`` は分値に掛ける係数 (分なら 1.0，時間なら 1/60)．
    """
    values = list(values_minutes)
    if not values:
        return ("minutes_ago", 1.0)
    spread = max(values) - min(values)
    if spread > _HOURS_UNIT_THRESHOLD_MIN:
        return ("hours_ago", 1.0 / 60.0)
    return ("minutes_ago", 1.0)
