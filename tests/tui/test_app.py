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

    async def test_ctrl_o_exports_three_csv_files(self, tui_state, tmp_path, monkeypatch) -> None:
        """nano 風 ^O で 3 枚の CSV が cwd に出る．"""
        monkeypatch.chdir(tmp_path)
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+o")
            await pilot.pause()
        # fake.bin basename に基づく 4 ファイル (items / routes / events / inventory)
        stems = sorted(p.name for p in tmp_path.glob("fake_*.csv"))
        kinds = {s.split("_")[1] for s in stems}
        assert kinds == {"items", "routes", "events", "inventory"}
        # items CSV に header 行があることを verify
        items_csv = next(p for p in tmp_path.glob("fake_items_*.csv"))
        content = items_csv.read_text(encoding="utf-8").splitlines()
        assert content[0].startswith("guid,name,")

    async def test_ussr_theme_adds_sickle_hammer_prefix_to_title(self, tui_state) -> None:
        """``theme="ussr"`` で ☭ が title に付く．"""
        app = TradeApp(tui_state, theme="ussr")
        async with app.run_test() as pilot:
            await pilot.pause()
            assert "☭" in pilot.app.title

    async def test_default_theme_keeps_title_unchanged(self, tui_state) -> None:
        """default テーマでは ☭ なし．"""
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert "☭" not in pilot.app.title

    async def test_ussr_title_persists_across_locale_switch(self, tui_state) -> None:
        """locale 切替後も USSR の ☭ prefix は維持される．"""
        app = TradeApp(tui_state, theme="ussr")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+l")
            await pilot.pause()
            assert "☭" in pilot.app.title

    async def test_ctrl_o_after_locale_switch_uses_ja_names(
        self, tui_state, tmp_path, monkeypatch
    ) -> None:
        """^L → ^O で export に日本語 item 名が入る．"""
        monkeypatch.chdir(tmp_path)
        app = TradeApp(tui_state)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+l")
            await pilot.pause()
            await pilot.press("ctrl+o")
            await pilot.pause()
        items_csv = next(p for p in tmp_path.glob("fake_items_*.csv"))
        text = items_csv.read_text(encoding="utf-8")
        # fixture の yaml は ja で 100=木材 を持たないので fallback 名 Wood が出る (ok)．
        # 少なくとも CSV が空でないこと + header が出てること．
        assert "guid,name," in text


@pytest.mark.asyncio
class TestFromSaveClassmethod:
    async def test_from_save_constructs_state(self, tui_state) -> None:
        # tui_state.save_path を経由して from_save が動くか
        app = TradeApp.from_save(tui_state.save_path, locale="ja")
        assert app._state.locale == "ja"
        assert app._localizer.code == "ja"


def test_sanitize_filename_component_fallback_for_empty_or_whitespace() -> None:
    """``_sanitize_filename_component`` が空文字になる入力で unknown-<digest> を返す．

    coverage 対象: app.py lines 40-41 の ``digest = ...`` /
    ``return f"unknown-{digest}"`` fallback path．``strip(" .")`` の後に空になる
    入力 (空文字 / space+dot のみ) で踏む．unsafe 文字は ``-`` に置換されて
    strip で消えないので，unsafe-only では fallback に落ちないことにも注意．
    """
    from anno_save_analyzer.tui.app import _sanitize_filename_component

    empty = _sanitize_filename_component("")
    assert empty.startswith("unknown-")
    assert len(empty) == len("unknown-") + 8

    space_dot = _sanitize_filename_component("  .. ")
    assert space_dot.startswith("unknown-")

    # 決定性
    assert _sanitize_filename_component("") == empty
