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


class TestTradeDiffCommand:
    def _make_before_after(self, tmp_path: Path) -> tuple[Path, Path]:
        before_inner = make_inner_filedb(
            {
                "route": [(7, 2088, 5, 0), (7, 2073, -3, 0)],
                "passive": [(99, 2142, 1, -10)],
            }
        )
        after_inner = make_inner_filedb(
            {
                "route": [
                    (7, 2088, 8, 0),
                    (7, 2073, -3, 0),
                    (7, 2174, 2, 0),
                ],  # 2088 changed, 2174 added
                "passive": [],  # 2142 removed
            }
        )
        before = tmp_path / "before.bin"
        before.write_bytes(wrap_as_outer([before_inner]))
        after = tmp_path / "after.bin"
        after.write_bytes(wrap_as_outer([after_inner]))
        return before, after

    def test_diff_by_item_hides_unchanged_by_default(self, tmp_path: Path) -> None:
        before, after = self._make_before_after(tmp_path)
        result = runner.invoke(
            app, ["trade", "diff", str(before), str(after), "--title", "anno117"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        guids = {row["guid"]: row for row in payload}
        # 2088 changed, 2174 added, 2142 removed, 2073 unchanged は hidden
        assert 2088 in guids and guids[2088]["status"] == "changed"
        assert 2174 in guids and guids[2174]["status"] == "added"
        assert 2142 in guids and guids[2142]["status"] == "removed"
        assert 2073 not in guids

    def test_diff_show_unchanged_includes_all(self, tmp_path: Path) -> None:
        before, after = self._make_before_after(tmp_path)
        result = runner.invoke(
            app,
            [
                "trade",
                "diff",
                str(before),
                str(after),
                "--title",
                "anno117",
                "--show-unchanged",
            ],
        )
        payload = json.loads(result.stdout)
        guids = {row["guid"] for row in payload}
        # unchanged 含むので 2073 も登場
        assert 2073 in guids

    def test_diff_by_route(self, tmp_path: Path) -> None:
        before, after = self._make_before_after(tmp_path)
        result = runner.invoke(
            app,
            ["trade", "diff", str(before), str(after), "--title", "anno117", "--by", "route"],
        )
        payload = json.loads(result.stdout)
        # route 7 は changed (amount 増)，passive partner 99 は removed
        by_route = {(row["route_id"], row["partner_kind"]): row for row in payload}
        assert ("7", "route") in by_route
        assert by_route[("7", "route")]["status"] == "changed"
        assert (None, "passive") in by_route
        assert by_route[(None, "passive")]["status"] == "removed"

    def test_diff_by_route_show_unchanged(self, tmp_path: Path) -> None:
        """same before/after で route 差分，show_unchanged で unchanged 行も出す．"""
        same_inner = make_inner_filedb({"route": [(7, 2088, 5, 0)]})
        save = tmp_path / "same.bin"
        save.write_bytes(wrap_as_outer([same_inner]))
        result = runner.invoke(
            app,
            [
                "trade",
                "diff",
                str(save),
                str(save),
                "--title",
                "anno117",
                "--by",
                "route",
                "--show-unchanged",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        # 同じセーブ同士なので全 unchanged．--show-unchanged で出る．
        assert len(payload) >= 1
        assert all(row["status"] == "unchanged" for row in payload)

    def test_diff_respects_locale(self, tmp_path: Path) -> None:
        before, after = self._make_before_after(tmp_path)
        result = runner.invoke(
            app,
            [
                "trade",
                "diff",
                str(before),
                str(after),
                "--title",
                "anno117",
                "--locale",
                "ja",
            ],
        )
        payload = json.loads(result.stdout)
        # 2088=イワシ (Sardines) should show Japanese name
        sardines = next(row for row in payload if row["guid"] == 2088)
        assert sardines["name"] == "イワシ"

    def test_diff_csv_format_not_supported(self, tmp_path: Path) -> None:
        before, after = self._make_before_after(tmp_path)
        result = runner.invoke(
            app,
            ["trade", "diff", str(before), str(after), "--title", "anno117", "--format", "csv"],
        )
        assert result.exit_code != 0
        assert isinstance(result.exception, NotImplementedError)


class TestTopLevelHelp:
    def test_no_args_shows_help_and_exits_nonzero(self) -> None:
        result = runner.invoke(app, [])
        # typer の no_args_is_help=True は非 0 で help 表示
        assert result.exit_code != 0
