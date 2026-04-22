"""trade.clock の単体テスト．"""

from __future__ import annotations

import pytest

from anno_save_analyzer.trade.clock import (
    TICKS_PER_MINUTE,
    latest_tick,
    minutes_relative_to,
    pick_time_unit,
)


class TestMinutesRelativeTo:
    def test_same_tick_is_zero(self) -> None:
        assert minutes_relative_to(1000, now_tick=1000) == pytest.approx(0.0)

    def test_past_tick_is_negative(self) -> None:
        # TPM ticks 前 = -1.0 分．TPM 自体の精度は clock.py docstring 参照．
        assert minutes_relative_to(1000 - TICKS_PER_MINUTE, now_tick=1000) == pytest.approx(-1.0)

    def test_future_tick_is_positive(self) -> None:
        # 理論上 future は無いが式としては正値で返る．
        assert minutes_relative_to(1000 + TICKS_PER_MINUTE, now_tick=1000) == pytest.approx(1.0)

    def test_ticks_per_minute_constant_is_60k(self) -> None:
        """1 tick = 1 ms 校正．clock.py docstring 参照．rolling buffer 2h
        観察 + 書記長エクスポート 12 行 fit で裏付け済 (2026-04-22)．"""
        assert TICKS_PER_MINUTE == 60_000


class TestLatestTick:
    def test_returns_max_of_non_empty(self) -> None:
        assert latest_tick([100, 500, 300]) == 500

    def test_returns_none_on_empty(self) -> None:
        assert latest_tick([]) is None


class TestPickTimeUnit:
    def test_empty_returns_minutes(self) -> None:
        unit, div = pick_time_unit([])
        assert unit == "minutes_ago"
        assert div == 1.0

    def test_small_spread_stays_in_minutes(self) -> None:
        unit, div = pick_time_unit([-30.0, 0.0, -15.0])
        assert unit == "minutes_ago"
        assert div == 1.0

    def test_just_under_threshold_is_minutes(self) -> None:
        # spread = 120 分ちょうどは minutes のまま (>120 で切替)
        unit, _ = pick_time_unit([-120.0, 0.0])
        assert unit == "minutes_ago"

    def test_large_spread_switches_to_hours(self) -> None:
        unit, div = pick_time_unit([-500.0, 0.0])
        assert unit == "hours_ago"
        assert div == pytest.approx(1.0 / 60.0)


class TestInventorySampleMinutes:
    def test_latest_sample_at_zero(self) -> None:
        from anno_save_analyzer.trade.clock import inventory_sample_minutes

        out = inventory_sample_minutes(5)
        assert out[-1] == 0.0
        # 最古サンプルは -(5-1)*1 = -4 分 (step=SAMPLE_INTERVAL_TICKS=TPM → 1 sample = 1 min)
        assert out[0] == -4.0
        # 昇順
        assert out == sorted(out)

    def test_single_sample_is_zero(self) -> None:
        from anno_save_analyzer.trade.clock import inventory_sample_minutes

        assert inventory_sample_minutes(1) == [0.0]

    def test_empty_returns_empty(self) -> None:
        from anno_save_analyzer.trade.clock import inventory_sample_minutes

        assert inventory_sample_minutes(0) == []

    def test_120_samples_span_two_hours(self) -> None:
        """書記長の dogfood 仮定: capacity=120 で 2 時間分の履歴 (step=600 ticks=1 分)．"""
        from anno_save_analyzer.trade.clock import inventory_sample_minutes

        out = inventory_sample_minutes(120)
        assert out[-1] == 0.0
        assert out[0] == -119.0
        # 最古から最新までの spread = 119 分 (≈ 2 時間)
        assert out[-1] - out[0] == 119.0

    def test_custom_step_ticks(self) -> None:
        """step を TPM/10 に渡すと 0.1 分刻みになる．TPM 依存の数値は式で表現．"""
        from anno_save_analyzer.trade.clock import inventory_sample_minutes

        step = TICKS_PER_MINUTE // 10
        out = inventory_sample_minutes(5, step_ticks=step)
        expected = [i * (step / TICKS_PER_MINUTE) for i in range(-4, 1)]
        assert out == pytest.approx(expected)
