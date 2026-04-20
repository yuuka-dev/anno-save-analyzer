"""``trade.chart_window`` 純関数のテスト．"""

from __future__ import annotations

from anno_save_analyzer.trade.chart_window import (
    ChartTimeWindow,
    filter_events,
    filter_inventory_minutes,
)
from anno_save_analyzer.trade.clock import TICKS_PER_MINUTE
from anno_save_analyzer.trade.models import Item, TradeEvent


def _ev(tick: int | None) -> TradeEvent:
    item = Item(guid=1, names={"en": "X"})
    return TradeEvent(item=item, amount=1, total_price=1, timestamp_tick=tick)


class TestChartTimeWindowEnum:
    def test_members_have_locale_key(self) -> None:
        for w in ChartTimeWindow:
            assert w.locale_key.startswith("chart.window.")

    def test_max_minutes_values(self) -> None:
        assert ChartTimeWindow.LAST_120_MIN.max_minutes == 120.0
        assert ChartTimeWindow.LAST_4H.max_minutes == 240.0
        assert ChartTimeWindow.LAST_12H.max_minutes == 720.0
        assert ChartTimeWindow.LAST_24H.max_minutes == 1440.0
        assert ChartTimeWindow.ALL.max_minutes is None

    def test_next_cycles_through_all_members(self) -> None:
        seen: list[ChartTimeWindow] = []
        current = ChartTimeWindow.LAST_120_MIN
        for _ in range(len(ChartTimeWindow)):
            seen.append(current)
            current = current.next()
        assert set(seen) == set(ChartTimeWindow)
        # cycle は元に戻る
        assert current == ChartTimeWindow.LAST_120_MIN


class TestFilterEvents:
    def test_all_keeps_everything_timed(self) -> None:
        events = [_ev(100), _ev(200), _ev(300)]
        out = filter_events(events, ChartTimeWindow.ALL)
        assert len(out) == 3

    def test_all_drops_tick_none(self) -> None:
        """``ALL`` でも ``timestamp_tick=None`` は chart に出せないので落とす．"""
        events = [_ev(100), _ev(None)]
        out = filter_events(events, ChartTimeWindow.ALL)
        assert len(out) == 1

    def test_120_min_cutoff(self) -> None:
        # 最新 tick = 1000000．120 分 = 72000 tick．cutoff = 928000．
        events = [
            _ev(1_000_000),  # 0 min ago  → keep
            _ev(1_000_000 - 60 * TICKS_PER_MINUTE),  # 60 min ago  → keep
            _ev(1_000_000 - 120 * TICKS_PER_MINUTE),  # 120 min ago → keep (境界)
            _ev(1_000_000 - 121 * TICKS_PER_MINUTE),  # 121 min ago → drop
        ]
        out = filter_events(events, ChartTimeWindow.LAST_120_MIN)
        ticks = sorted(e.timestamp_tick for e in out)
        assert ticks == [
            1_000_000 - 120 * TICKS_PER_MINUTE,
            1_000_000 - 60 * TICKS_PER_MINUTE,
            1_000_000,
        ]

    def test_empty_input_returns_empty(self) -> None:
        assert filter_events([], ChartTimeWindow.LAST_120_MIN) == []

    def test_no_timed_events_returns_empty_list(self) -> None:
        """``timestamp_tick=None`` しかない場合は (now_tick が立たず) 全 drop．"""
        events = [_ev(None), _ev(None)]
        out = filter_events(events, ChartTimeWindow.LAST_120_MIN)
        assert out == []

    def test_iterator_input_is_supported(self) -> None:
        """iterable が generator でも 2-pass で消費されず正しく残る．"""
        events = (_ev(t) for t in (100, 200, 300))
        out = filter_events(events, ChartTimeWindow.ALL)
        assert [e.timestamp_tick for e in out] == [100, 200, 300]


class TestFilterInventoryMinutes:
    def test_all_keeps_everything(self) -> None:
        minutes = [-2.0, -1.0, 0.0]
        idx, kept = filter_inventory_minutes(minutes, ChartTimeWindow.ALL)
        assert idx == [0, 1, 2]
        assert kept == minutes

    def test_120_min_cuts_oldest(self) -> None:
        # 121 サンプル (0..-120 分)．120 分窓で全部残る (境界包含)．
        minutes = [-float(i) for i in range(120, -1, -1)]
        idx, kept = filter_inventory_minutes(minutes, ChartTimeWindow.LAST_120_MIN)
        assert len(kept) == 121
        assert idx[0] == 0 and idx[-1] == 120

    def test_24h_window_with_short_samples(self) -> None:
        # 10 サンプルでは 24h は効果なし
        minutes = [-float(i) for i in range(9, -1, -1)]
        idx, kept = filter_inventory_minutes(minutes, ChartTimeWindow.LAST_24H)
        assert kept == minutes
        assert idx == list(range(10))

    def test_4h_window_cuts_older_than_240(self) -> None:
        minutes = [-300.0, -240.0, -120.0, 0.0]
        idx, kept = filter_inventory_minutes(minutes, ChartTimeWindow.LAST_4H)
        assert kept == [-240.0, -120.0, 0.0]
        assert idx == [1, 2, 3]
