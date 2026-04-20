"""ゲーム内 tick ↔ 実時間 (分) 換算．

Anno 1800 / 117 の内部 tick はシミュレーション歩進単位．書記長の
``sample_anno1800.a7s`` を Anno 1800 で開き，取引履歴 UI の「N 分前」表記と
save 内の ``timestamp_tick`` を突き合わせて校正した:

=========================  =====  ===========================
Δtick (最新取引との差)     UI 分  備考
=========================  =====  ===========================
     2,700                    2    （近傍．UI 丸めで分精度）
    17,400                    3
   101,000                    5
   500,400                   12
 1,000,300                   20
=========================  =====  ===========================

5 点最小二乗 fit で ``slope ≈ 1.76e-5 min/tick`` → **TPM ≈ 57,000
tick/分**．切片 ≈ 2.7 分は Anno 1800 がゲーム停止できない仕様で書記長が UI
を確認している間に進んだ tick 分．``sample_anno117.a8s`` は同じ係数で
``range ≈ 3.5 h`` になり，書記長のプレイ感と整合する．タイトル固有に
差が出たら ``interpreter`` 層で override すればよい．
"""

from __future__ import annotations

from collections.abc import Iterable

# 1 分あたりの tick 数．
# 校正: sample_anno1800.a7s UI との 5 点対応から fit した値．docstring 参照．
# 旧仮定 (600) は在庫 120 サンプル ≈ 2h という UI 観察からの逆算だったが，
# 取引履歴 UI との突き合わせで ~95 倍大きいことが判明．
TICKS_PER_MINUTE = 57_000

# ``StorageTrends > Points`` の 1 サンプル = 何 tick か．
# 在庫 UI 観察で「120 サンプル ≈ 2 時間」が書記長確認済．``TICKS_PER_MINUTE``
# の校正後もこの観察は崩れない (偶然 1 サンプル ≈ 1 分のまま)．将来在庫側
# だけ粒度が変わった場合はここで分岐させる．
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
