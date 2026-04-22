"""ゲーム内 tick ↔ 実時間 (分) 換算．

Anno 1800 / 117 の内部 tick はシミュレーション歩進単位．**1 tick = 1 ms**
とするのが正解 (つまり ``TICKS_PER_MINUTE = 60_000``)．根拠は 2 つ:

1. **Rolling history buffer が 2 時間固定**．実測で ``sample_anno1800.a7s``
   の timestamp_tick spread = 7,199,400，``sample_anno117.a8s`` = 7,199,000．
   どちらも本質的に 7,200,000 = 120 × 60,000 で，2 時間ちょうどの
   rolling buffer を強く示唆する．

2. **書記長実セーブのエクスポート 12 行に対する最小二乗 fit** (2026-04-22):

   =========================  =======  ============================
   Δtick (oldest - newest)    Δ 分前  TPM (= Δtick / Δmin)
   =========================  =======  ============================
    5,191,900                 84      61,808
   =========================  =======  ============================

   線形 fit は TPM ≈ 60,800．±1 min の丸め誤差を考慮すると TPM = 60,000
   に収束する．

旧値 ``TICKS_PER_MINUTE = 57,000`` は別の save の UI ``N 分前`` 表示を 5 点
見て fit した値だったが，UI 値が整数丸めで ±1 分精度のため fit の標準誤差が
大きく ~6% 外した．12 行のエクスポートと buffer 観察で 60_000 に訂正．

**注**: 取引履歴 UI が示す「X 分前」は save-time tick (= ゲーム save 時点の
now_tick) 基準だが，本 tool は ``max(recent event tick)`` を基準にしとる．
そのため最新イベントの表示は常に "0 分前" となり，ゲーム UI とは save-time
と max-event-tick の差分 (書記長セーブで ~5 分) だけ系統的にズレる．
save-time 基準への切替は別途 issue 化の予定．
"""

from __future__ import annotations

from collections.abc import Iterable

# 1 分あたりの tick 数．1 tick = 1 ms で 60,000．docstring 参照．
TICKS_PER_MINUTE = 60_000

# ``StorageTrends > Points`` の 1 サンプル = 何 tick か．実測 UI の
# 「120 サンプル ≈ 2 時間」観察から TPM と一致する (1 sample = 1 min)．
SAMPLE_INTERVAL_TICKS = TICKS_PER_MINUTE  # 1 sample = 1 minute


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

    最新サンプル (``samples[-1]``) を 0，最古を
    ``-(n_samples - 1) * step_ticks / TICKS_PER_MINUTE`` として左に並べる．
    chart の x 軸は昇順なので最古が左端．
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
