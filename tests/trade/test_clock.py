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
        # 600 ticks 前 = -1.0 分
        assert minutes_relative_to(400, now_tick=1000) == pytest.approx(-1.0)

    def test_future_tick_is_positive(self) -> None:
        # 理論上 future は無いが式としては正値で返る
        assert minutes_relative_to(1600, now_tick=1000) == pytest.approx(1.0)

    def test_ticks_per_minute_constant_is_600(self) -> None:
        """Anno 1 tick ≈ 100 ms = 600 ticks/min の仮定を文書化テスト．"""
        assert TICKS_PER_MINUTE == 600


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
