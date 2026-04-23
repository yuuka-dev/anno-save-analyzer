"""``anno-save-analyzer state`` の JSON export テスト．

合成 save で pipeline を通し，JSON の構造が期待通りかを確認する．
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from anno_save_analyzer.cli.__main__ import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def synthetic_save(tmp_path: Path) -> Path:
    """TUI test fixtures と同じ合成 inner FileDB で保存 file を作る．"""
    from tests.trade.conftest import make_inner_filedb, wrap_as_outer

    inner_a = make_inner_filedb({"route": [(7, 100, 5, 0), (7, 200, -3, 0)]})
    inner_b = make_inner_filedb({"route": [(8, 200, 2, 0)]})
    outer = wrap_as_outer([inner_a, inner_b])
    save = tmp_path / "fake.bin"
    save.write_bytes(outer)
    return save


@pytest.fixture
def synth_items_dir(tmp_path: Path) -> Path:
    """117 タイトル向けの最小 items YAML を data dir に用意．"""
    (tmp_path / "items_anno117.en.yaml").write_text(
        "100:\n  name: Wood\n  category: raw\n200:\n  name: Bricks\n",
        encoding="utf-8",
    )
    (tmp_path / "items_anno117.ja.yaml").write_text(
        "100:\n  name: 木材\n200:\n  name: 煉瓦\n",
        encoding="utf-8",
    )
    return tmp_path


def test_state_command_writes_expected_toplevel_keys(
    runner: CliRunner, synthetic_save: Path, tmp_path: Path, monkeypatch
) -> None:
    """117 合成 save で state コマンドが JSON を書き，既知 top-level キーが揃う．"""
    out = tmp_path / "state.json"
    # items YAML は packaged を使わせる (117 packaged は repo に存在するのでそのまま)
    result = runner.invoke(
        app,
        [
            "state",
            str(synthetic_save),
            "--title",
            "anno117",
            "--locale",
            "en",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert set(data) >= {"save", "title", "locale", "overview", "islands", "trade_events"}
    assert data["title"] == "anno117"
    assert data["locale"] == "en"
    assert isinstance(data["trade_events"], list)


def test_state_command_no_events_flag_drops_ledger(
    runner: CliRunner, synthetic_save: Path, tmp_path: Path
) -> None:
    """``--no-events`` で ``trade_events`` が ``null`` になる．"""
    out = tmp_path / "state.json"
    result = runner.invoke(
        app,
        [
            "state",
            str(synthetic_save),
            "--title",
            "anno117",
            "--no-events",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["trade_events"] is None


def test_state_command_compact_indent(
    runner: CliRunner, synthetic_save: Path, tmp_path: Path
) -> None:
    """``--indent 0`` で compact JSON．改行なしであることを確認．"""
    out = tmp_path / "state.json"
    result = runner.invoke(
        app,
        [
            "state",
            str(synthetic_save),
            "--title",
            "anno117",
            "--indent",
            "0",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    # indent=0 なら改行文字数が 1 行分のみ (end newline は json.dumps で付かない)
    assert "\n" not in text


def test_state_command_missing_save_fails(runner: CliRunner, tmp_path: Path) -> None:
    """存在しない save path は click の ``exists=True`` で落ちる．"""
    out = tmp_path / "state.json"
    result = runner.invoke(
        app,
        [
            "state",
            str(tmp_path / "does_not_exist.a7s"),
            "--title",
            "anno117",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code != 0
    assert not out.exists()
