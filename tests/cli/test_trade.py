"""``trade`` CLI subcommand のテスト．"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from anno_save_analyzer.cli import app
from tests.trade.conftest import make_inner_filedb, wrap_as_outer

runner = CliRunner()


def _make_save(tmp_path: Path) -> Path:
    inner = make_inner_filedb(
        {
            "route": [(7, 2088, 5, 0), (7, 2073, -3, 0)],
            "passive": [(99, 2142, 1, -10)],
        }
    )
    outer = wrap_as_outer([inner])
    save = tmp_path / "fake.bin"
    save.write_bytes(outer)
    return save


class TestTradeListCommand:
    def test_outputs_json_array_with_events(self, tmp_path: Path) -> None:
        save = _make_save(tmp_path)
        result = runner.invoke(app, ["trade", "list", str(save)])
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert isinstance(payload, list)
        assert len(payload) == 3
        first = payload[0]
        assert "item" in first
        assert first["item"]["guid"] in {2088, 2073, 2142}

    def test_locale_changes_item_name(self, tmp_path: Path) -> None:
        # packaged ja yaml で 2088=イワシ (GUID 2088 は Sardines)
        save = _make_save(tmp_path)
        result = runner.invoke(
            app, ["trade", "list", str(save), "--title", "anno117", "--locale", "ja"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        sardines = next(p for p in payload if p["item"]["guid"] == 2088)
        assert sardines["item"]["name"] == "イワシ"


class TestTradeSummaryCommand:
    def test_summary_by_item(self, tmp_path: Path) -> None:
        save = _make_save(tmp_path)
        result = runner.invoke(app, ["trade", "summary", str(save), "--by", "item"])
        assert result.exit_code == 0
        rows = json.loads(result.stdout)
        guids = {r["guid"] for r in rows}
        assert guids == {2088, 2073, 2142}

    def test_summary_by_route(self, tmp_path: Path) -> None:
        save = _make_save(tmp_path)
        result = runner.invoke(app, ["trade", "summary", str(save), "--by", "route"])
        assert result.exit_code == 0
        rows = json.loads(result.stdout)
        kinds = {r["partner_kind"] for r in rows}
        assert "route" in kinds
        assert "passive" in kinds


class TestUnsupportedFormatYet:
    """v0.3.0 Week 1 では JSON のみ対応．他は明示的に NotImplementedError．"""

    def test_csv_format_not_yet_supported_for_list(self, tmp_path: Path) -> None:
        save = _make_save(tmp_path)
        result = runner.invoke(app, ["trade", "list", str(save), "--format", "csv"])
        assert result.exit_code != 0
        # typer は exception 発生時に非 0 で exit．exception 内容は exception 経由で取れる
        assert result.exception is not None
        assert isinstance(result.exception, NotImplementedError)

    def test_html_format_not_yet_supported_for_summary(self, tmp_path: Path) -> None:
        save = _make_save(tmp_path)
        result = runner.invoke(app, ["trade", "summary", str(save), "--format", "html"])
        assert result.exit_code != 0
        assert isinstance(result.exception, NotImplementedError)


class TestTopLevelHelp:
    def test_no_args_shows_help_and_exits_nonzero(self) -> None:
        result = runner.invoke(app, [])
        # typer の no_args_is_help=True は非 0 で help 表示
        assert result.exit_code != 0
