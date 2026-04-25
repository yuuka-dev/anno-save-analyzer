"""``anno-save-analyzer-gui`` entry の save 解決テスト．

実 Qt event loop は起動せず，``QApplication`` / ``main_window``
を mock して main() の早期 return パスだけを叩く．
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from anno_save_analyzer.gui import __main__ as gui_main


def _synth_save(tmp_path: Path) -> Path:
    from tests.trade.conftest import make_inner_filedb, wrap_as_outer

    inner = make_inner_filedb({"route": [(7, 100, 5, 0)]})
    save = tmp_path / "fake.a8s"
    save.write_bytes(wrap_as_outer([inner]))
    return save


def test_gui_main_save_omitted_no_config(tmp_path: Path, monkeypatch, capsys) -> None:
    """save 省略 + config に paths 未設定 → exit 2 + ガイドメッセージ．"""
    cfg = tmp_path / "cfg.toml"
    cfg.write_text("[ui]\n", encoding="utf-8")
    monkeypatch.setenv("ANNO_SAVE_ANALYZER_CONFIG", str(cfg))

    rc = gui_main.main(["--title", "anno1800"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "anno1800_save_dir" in err
    assert "config.toml" in err


def test_gui_main_explicit_missing_path_returns_2(tmp_path: Path, capsys) -> None:
    """明示指定された path が存在しない → exit 2 + ``save file not found``．"""
    rc = gui_main.main([str(tmp_path / "nope.a7s"), "--title", "anno1800"])
    assert rc == 2
    assert "save file not found" in capsys.readouterr().err


def test_gui_main_save_omitted_picks_latest(tmp_path: Path, monkeypatch, capsys) -> None:
    """save 省略 + config 設定済 → 最新 save を選び GUI を起動．

    PySide6 が **install されてない CI 環境でも動かす** ため，``sys.modules``
    に MagicMock を inject して ``from PySide6.QtGui import QFont`` 等の
    遅延 import を吸収する．書記長 GUI extra (``[gui]``) は dev group のみ．
    """
    save_dir = tmp_path / "saves"
    save_dir.mkdir()
    save = save_dir / "auto.a8s"
    save.write_bytes(_synth_save(tmp_path).read_bytes())

    cfg = tmp_path / "cfg.toml"
    cfg.write_text(f'[paths]\nanno117_save_dir = "{save_dir}"\n', encoding="utf-8")
    monkeypatch.setenv("ANNO_SAVE_ANALYZER_CONFIG", str(cfg))

    fake_pyside6 = MagicMock()
    fake_qtgui = MagicMock()
    fake_qtwidgets = MagicMock()
    fake_qtwidgets.QApplication.instance.return_value = None
    fake_main_window = MagicMock()

    sys_modules_patch = {
        "PySide6": fake_pyside6,
        "PySide6.QtGui": fake_qtgui,
        "PySide6.QtWidgets": fake_qtwidgets,
        "anno_save_analyzer.gui.main_window": fake_main_window,
    }

    with (
        patch.dict(sys.modules, sys_modules_patch),
        patch.object(gui_main, "load_state", return_value=object()),
        patch.object(gui_main, "_run_qt_event_loop", return_value=0) as loop_mock,
    ):
        rc = gui_main.main(["--title", "anno117"])

    assert rc == 0
    err = capsys.readouterr().err
    assert "Auto-selected latest save" in err
    assert "auto.a8s" in err
    loop_mock.assert_called_once()
