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
    save = tmp_path / "fake.bin"
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
