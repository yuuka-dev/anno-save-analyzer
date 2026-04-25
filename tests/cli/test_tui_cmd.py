"""``anno-save-analyzer tui`` CLI のテスト．"""

from __future__ import annotations

import builtins
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from anno_save_analyzer.cli import app
from tests.trade.conftest import make_inner_filedb, wrap_as_outer

runner = CliRunner()


def _make_save(tmp_path: Path) -> Path:
    inner = make_inner_filedb({"route": [(7, 2088, 5, 0)]})
    save = tmp_path / "fake.a8s"
    save.write_bytes(wrap_as_outer([inner]))
    return save


class TestTuiCommand:
    def test_tui_shows_friendly_error_when_textual_missing(self, tmp_path: Path) -> None:
        save = _make_save(tmp_path)
        original_import = builtins.__import__

        def raising_import(name, *args, **kwargs):
            if name == "anno_save_analyzer.tui":
                raise ImportError("No module named 'textual'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=raising_import):
            result = runner.invoke(app, ["tui", str(save)])
        assert result.exit_code == 1
        assert "anno-save-analyzer[tui]" in result.output

    def test_tui_subcommand_invokes_app(self, tmp_path: Path) -> None:
        save = _make_save(tmp_path)
        # TradeApp.run() を mock して headless で実行終了
        with patch("anno_save_analyzer.tui.TradeApp.run") as run_mock:
            result = runner.invoke(app, ["tui", str(save), "--locale", "ja"])
        assert result.exit_code == 0, result.stdout
        run_mock.assert_called_once()

    def test_tui_default_locale_is_en(self, tmp_path: Path) -> None:
        save = _make_save(tmp_path)
        with patch("anno_save_analyzer.tui.TradeApp.run") as run_mock:
            result = runner.invoke(app, ["tui", str(save)])
        assert result.exit_code == 0
        run_mock.assert_called_once()

    def test_tui_emits_progress_labels(self, tmp_path: Path) -> None:
        """ロード中にステージ進捗が出力される (typer は stderr を stdout にマージ)．"""
        save = _make_save(tmp_path)
        with patch("anno_save_analyzer.tui.TradeApp.run"):
            result = runner.invoke(app, ["tui", str(save), "--title", "anno117"])
        assert result.exit_code == 0, result.output
        out = result.output
        # ``Loading …`` ヘッダと少なくとも 1 つのステージラベル，完了マーク
        assert "Loading" in out
        assert "…" in out
        assert "ready" in out

    def test_tui_gauge_survives_truncated_progress(self, tmp_path: Path) -> None:
        """load_state が途中で抜けても (callback 呼び数 < 5) gauge が exit 1 を起こさない．

        bar は途中までしか進まないのが仕様 (書記長方針: データ量粒度で正直に)．
        100% 到達は要件ではなく，exit コード 0 で抜けられることだけを保証する．
        """
        save = _make_save(tmp_path)

        def fake_load_state(*args, **kwargs):
            cb = kwargs.get("progress")
            if cb:
                cb("stage one")
                cb("stage two")
            return object()

        with (
            patch("anno_save_analyzer.tui.state.load_state", fake_load_state),
            patch(
                "anno_save_analyzer.tui.TradeApp.__init__",
                lambda self, *_, **__: None,
            ),
            patch("anno_save_analyzer.tui.TradeApp.run"),
        ):
            result = runner.invoke(app, ["tui", str(save)])
        assert result.exit_code == 0, result.output
        assert "ready" in result.output

    def test_tui_ussr_theme_passes_through(self, tmp_path: Path) -> None:
        """``--theme ussr`` で TradeApp が ☭ 付 title で起動．"""
        save = _make_save(tmp_path)
        captured: dict[str, object] = {}

        def fake_init(self, state, *, localizer=None, theme="default", persist_settings=False):
            captured["theme"] = theme
            captured["persist_settings"] = persist_settings
            # super().__init__ は呼ばないと run() がコケるが run は mock 済なので
            # 最小限の set だけで通す．
            from anno_save_analyzer.tui.i18n import Localizer

            self._state = state
            self._localizer = localizer or Localizer.load(state.locale)
            self._theme_name = theme

        with (
            patch("anno_save_analyzer.tui.TradeApp.__init__", fake_init),
            patch("anno_save_analyzer.tui.TradeApp.run"),
        ):
            result = runner.invoke(app, ["tui", str(save), "--theme", "ussr"])
        assert result.exit_code == 0
        assert captured["theme"] == "ussr"
        # CLI 起動時は config.toml への自動書き出しを有効化している
        assert captured["persist_settings"] is True

    def test_tui_reads_saved_config_for_locale_and_theme(self, tmp_path: Path, monkeypatch) -> None:
        """``--locale`` / ``--theme`` 無指定なら ``config.toml`` 値が使われる．"""
        cfg_path = tmp_path / "cfg.toml"
        cfg_path.write_text(
            '[ui]\nlocale = "ja"\ntheme = "ussr"\nchart_window = "24h"\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("ANNO_SAVE_ANALYZER_CONFIG", str(cfg_path))
        save = _make_save(tmp_path)

        captured: dict[str, object] = {}

        def fake_init(self, state, *, localizer=None, theme="default", persist_settings=False):
            captured["theme"] = theme
            captured["state_locale"] = state.locale
            from anno_save_analyzer.tui.i18n import Localizer

            self._state = state
            self._localizer = localizer or Localizer.load(state.locale)
            self._theme_name = theme

        with (
            patch("anno_save_analyzer.tui.TradeApp.__init__", fake_init),
            patch("anno_save_analyzer.tui.TradeApp.run"),
        ):
            result = runner.invoke(app, ["tui", str(save)])

        assert result.exit_code == 0, result.output
        assert captured["theme"] == "ussr"
        assert captured["state_locale"] == "ja"

    def test_tui_cli_arg_overrides_config(self, tmp_path: Path, monkeypatch) -> None:
        """config.toml より CLI ``--locale`` 引数を優先する．"""
        cfg_path = tmp_path / "cfg.toml"
        cfg_path.write_text('[ui]\nlocale = "ja"\n', encoding="utf-8")
        monkeypatch.setenv("ANNO_SAVE_ANALYZER_CONFIG", str(cfg_path))
        save = _make_save(tmp_path)

        captured: dict[str, object] = {}

        def fake_init(self, state, *, localizer=None, theme="default", persist_settings=False):
            captured["state_locale"] = state.locale
            from anno_save_analyzer.tui.i18n import Localizer

            self._state = state
            self._localizer = localizer or Localizer.load(state.locale)
            self._theme_name = theme

        with (
            patch("anno_save_analyzer.tui.TradeApp.__init__", fake_init),
            patch("anno_save_analyzer.tui.TradeApp.run"),
        ):
            result = runner.invoke(app, ["tui", str(save), "--locale", "en"])

        assert result.exit_code == 0
        assert captured["state_locale"] == "en"

    def test_tui_save_omitted_without_title_fails(self, tmp_path: Path, monkeypatch) -> None:
        """save 省略 + ``--title`` 未指定 → exit 2 + ``--title`` 要求メッセージ．"""
        cfg = tmp_path / "cfg.toml"
        cfg.write_text("", encoding="utf-8")
        monkeypatch.setenv("ANNO_SAVE_ANALYZER_CONFIG", str(cfg))
        result = runner.invoke(app, ["tui"])
        assert result.exit_code == 2
        assert "--title" in result.output

    def test_tui_save_omitted_no_config_path_fails(self, tmp_path: Path, monkeypatch) -> None:
        """save 省略 + ``--title`` あり + config に paths 未設定 → exit 2 + ガイド．"""
        cfg = tmp_path / "cfg.toml"
        cfg.write_text("[ui]\n", encoding="utf-8")
        monkeypatch.setenv("ANNO_SAVE_ANALYZER_CONFIG", str(cfg))
        result = runner.invoke(app, ["tui", "--title", "anno1800"])
        assert result.exit_code == 2
        assert "anno1800_save_dir" in result.output

    def test_tui_save_omitted_picks_latest_from_config(self, tmp_path: Path, monkeypatch) -> None:
        """save 省略 + config 設定済 → 最新 save を自動選択して TUI 起動．"""
        save_dir = tmp_path / "saves"
        save_dir.mkdir()
        save = save_dir / "auto.a8s"
        save.write_bytes(_make_save(tmp_path).read_bytes())

        cfg = tmp_path / "cfg.toml"
        cfg.write_text(f'[paths]\nanno117_save_dir = "{save_dir}"\n', encoding="utf-8")
        monkeypatch.setenv("ANNO_SAVE_ANALYZER_CONFIG", str(cfg))

        with patch("anno_save_analyzer.tui.TradeApp.run"):
            result = runner.invoke(app, ["tui", "--title", "anno117"])
        assert result.exit_code == 0, result.output
        assert "Auto-selected latest save" in result.output
        assert "auto.a8s" in result.output

    def test_tui_warns_on_unknown_theme_in_config(self, tmp_path: Path, monkeypatch) -> None:
        """破損 theme 値は default にフォールバックし warning を出す．"""
        cfg_path = tmp_path / "cfg.toml"
        cfg_path.write_text('[ui]\ntheme = "neonpunk"\n', encoding="utf-8")
        monkeypatch.setenv("ANNO_SAVE_ANALYZER_CONFIG", str(cfg_path))
        save = _make_save(tmp_path)

        captured: dict[str, object] = {}

        def fake_init(self, state, *, localizer=None, theme="default", persist_settings=False):
            captured["theme"] = theme
            from anno_save_analyzer.tui.i18n import Localizer

            self._state = state
            self._localizer = localizer or Localizer.load(state.locale)
            self._theme_name = theme

        with (
            patch("anno_save_analyzer.tui.TradeApp.__init__", fake_init),
            patch("anno_save_analyzer.tui.TradeApp.run"),
        ):
            result = runner.invoke(app, ["tui", str(save)])

        assert result.exit_code == 0, result.output
        assert captured["theme"] == "default"
        assert "unknown theme" in result.output
