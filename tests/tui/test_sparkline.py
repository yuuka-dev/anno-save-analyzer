"""tui.sparkline の単体テスト．"""

from __future__ import annotations

from anno_save_analyzer.tui.sparkline import sparkline


class TestSparkline:
    def test_empty_input_returns_single_lowest_block(self) -> None:
        s = sparkline([])
        assert len(s) == 1
        assert s == "▁"

    def test_flat_values_return_midblock(self) -> None:
        s = sparkline([5, 5, 5, 5])
        assert len(s) == 4
        assert set(s) == {"▅"}  # 中段 = BLOCKS[4] (len 8 なので 8//2=4)

    def test_monotonic_increasing_uses_full_range(self) -> None:
        s = sparkline([0, 1, 2, 3, 4, 5, 6, 7])
        assert s[0] == "▁"
        assert s[-1] == "█"
        assert len(s) == 8

    def test_longer_than_width_is_downsampled(self) -> None:
        # 100 要素 → width=12 に等間隔サンプリング
        s = sparkline(range(100), width=12)
        assert len(s) == 12
        assert s[0] == "▁"
        assert s[-1] == "█"

    def test_shorter_than_width_keeps_all_samples(self) -> None:
        s = sparkline([1, 2, 3], width=12)
        assert len(s) == 3

    def test_negative_values_normalise_correctly(self) -> None:
        s = sparkline([-5, 0, 5])
        assert s[0] == "▁"
        assert s[-1] == "█"

    def test_custom_width_respected_when_downsampling(self) -> None:
        s = sparkline(range(50), width=5)
        assert len(s) == 5
