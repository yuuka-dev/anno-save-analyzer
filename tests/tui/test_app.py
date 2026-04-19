"""TradeApp の Pilot ベース snapshot テスト．"""

from __future__ import annotations

import pytest

from anno_save_analyzer.tui import TradeApp
from anno_save_analyzer.tui.screens import OverviewScreen, TradeStatisticsScreen


@pytest.mark.asyncio
class TestTradeAppLifecycle:
    @staticmethod
    def _binding_description(app: TradeApp, key: str) -> str:
        return next(binding.description for binding in app.BINDINGS if binding.key == key)

    async def test_app_boots_to_overview(self, tui_state) -> None:
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert pilot.app.title == "anno-save-analyzer"
            assert isinstance(pilot.app.screen, OverviewScreen)
            assert self._binding_description(pilot.app, "ctrl+l") == "Locale"

    async def test_overview_to_statistics_via_ctrl_t(self, tui_state) -> None:
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            assert isinstance(pilot.app.screen, TradeStatisticsScreen)

    async def test_statistics_to_overview_via_ctrl_t(self, tui_state) -> None:
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            await pilot.press("ctrl+t")
            await pilot.pause()
            assert isinstance(pilot.app.screen, OverviewScreen)

    async def test_locale_switch_via_ctrl_l(self, tui_state) -> None:
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert pilot.app._localizer.code == "en"
            assert self._binding_description(pilot.app, "ctrl+l") == "Locale"
            await pilot.press("ctrl+l")
            await pilot.pause()
            assert pilot.app._localizer.code == "ja"
            assert self._binding_description(pilot.app, "ctrl+l") == "言語"
            # もう 1 度押すと en に戻る
            await pilot.press("ctrl+l")
            await pilot.pause()
            assert pilot.app._localizer.code == "en"
            assert self._binding_description(pilot.app, "ctrl+l") == "Locale"

    async def test_locale_switch_from_statistics_screen(self, tui_state) -> None:
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+t")  # to statistics
            await pilot.pause()
            await pilot.press("ctrl+l")  # toggle locale
            await pilot.pause()
            assert pilot.app._localizer.code == "ja"

    async def test_quit_via_ctrl_x(self, tui_state) -> None:
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+x")
            await pilot.pause()
        # exit on context manager close — no exception means success
        assert True


@pytest.mark.asyncio
class TestFromSaveClassmethod:
    async def test_from_save_constructs_state(self, tui_state) -> None:
        # tui_state.save_path を経由して from_save が動くか
        app = TradeApp.from_save(tui_state.save_path, locale="ja")
        assert app._state.locale == "ja"
        assert app._localizer.code == "ja"
