"""``anno_save_analyzer.config`` の単体テスト．"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from anno_save_analyzer.config import (
    _ENV_OVERRIDE,
    PathsConfig,
    UiConfig,
    UserConfig,
    chart_window_from_token,
    chart_window_to_token,
    default_config_path,
    load_config,
    save_config,
)
from anno_save_analyzer.trade.chart_window import ChartTimeWindow


class TestChartWindowTokens:
    def test_roundtrip_for_every_member(self) -> None:
        for window in ChartTimeWindow:
            token = chart_window_to_token(window)
            assert chart_window_from_token(token) == window

    def test_unknown_token_is_none(self) -> None:
        assert chart_window_from_token("nope") is None


class TestDefaultConfigPath:
    def test_env_override_takes_priority(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        override = tmp_path / "override.toml"
        monkeypatch.setenv(_ENV_OVERRIDE, str(override))
        assert default_config_path() == override

    def test_xdg_config_home_respected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv(_ENV_OVERRIDE, raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setattr("sys.platform", "linux")
        result = default_config_path()
        assert result == tmp_path / "anno-save-analyzer" / "config.toml"

    def test_default_linux_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv(_ENV_OVERRIDE, raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr("sys.platform", "linux")
        result = default_config_path()
        assert result == tmp_path / ".config" / "anno-save-analyzer" / "config.toml"


class TestLoadConfig:
    def test_missing_file_returns_default(self, tmp_path: Path) -> None:
        cfg = load_config(tmp_path / "missing.toml")
        assert cfg == UserConfig()

    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "cfg.toml"
        cfg = UserConfig(
            ui=UiConfig(
                locale="ja",
                theme="ussr",
                chart_window=chart_window_to_token(ChartTimeWindow.LAST_24H),
                recent_window_minutes=60.0,
            )
        )
        saved = save_config(cfg, path)
        assert saved == path
        loaded = load_config(path)
        assert loaded.ui.locale == "ja"
        assert loaded.ui.theme == "ussr"
        assert loaded.ui.chart_window == "24h"
        assert loaded.ui.recent_window_minutes == 60.0

    def test_broken_toml_falls_back_to_default(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "broken.toml"
        path.write_text("this is [not valid toml", encoding="utf-8")
        cfg = load_config(path)
        assert cfg == UserConfig()
        assert "could not be read" in capsys.readouterr().err

    def test_unknown_keys_are_ignored(self, tmp_path: Path) -> None:
        """``extra = ignore`` なので未知キーは無視される．"""
        path = tmp_path / "extra.toml"
        path.write_text(
            '[ui]\nlocale = "en"\ntheme = "default"\nchart_window = "all"\n'
            'unknown_field = "keep moving"\n',
            encoding="utf-8",
        )
        cfg = load_config(path)
        assert cfg.ui.locale == "en"
        assert cfg.ui.chart_window == "all"

    def test_invalid_field_type_falls_back_to_default(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "badtype.toml"
        # locale は str 前提．数値を入れて ValidationError を誘発
        path.write_text("[ui]\nlocale = 42\n", encoding="utf-8")
        cfg = load_config(path)
        assert cfg == UserConfig()
        assert "invalid fields" in capsys.readouterr().err


class TestSaveConfig:
    def test_atomic_write_replaces_existing(self, tmp_path: Path) -> None:
        path = tmp_path / "cfg.toml"
        path.write_text("[ui]\nlocale = 'en'\n", encoding="utf-8")
        save_config(UserConfig(ui=UiConfig(locale="ja")), path)
        assert "locale = " in path.read_text()
        assert load_config(path).ui.locale == "ja"

    def test_write_failure_returns_none(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # 書けないディレクトリ (既存 file を parent にすると mkdir が失敗)
        blocker = tmp_path / "blocked"
        blocker.write_text("x", encoding="utf-8")
        target = blocker / "config.toml"
        result = save_config(UserConfig(), target)
        assert result is None
        assert "cannot" in capsys.readouterr().err

    def test_write_failure_in_body_returns_none(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """tmp file の書き込み中に OSError が出た場合の fallback パス．"""
        path = tmp_path / "cfg.toml"

        original_replace = Path.replace

        def failing_replace(self: Path, target: os.PathLike[str]) -> Path:
            raise OSError("disk full")

        monkeypatch.setattr(Path, "replace", failing_replace)
        try:
            result = save_config(UserConfig(), path)
            assert result is None
            assert "cannot write" in capsys.readouterr().err
        finally:
            monkeypatch.setattr(Path, "replace", original_replace)

    def test_recent_window_none_is_commented_out(self, tmp_path: Path) -> None:
        path = tmp_path / "cfg.toml"
        save_config(UserConfig(ui=UiConfig(recent_window_minutes=None)), path)
        text = path.read_text(encoding="utf-8")
        assert "# recent_window_minutes" in text

    def test_special_chars_in_locale_are_escaped(self, tmp_path: Path) -> None:
        """TOML 文字列内の quote / backslash は escape されなければならない．"""
        path = tmp_path / "cfg.toml"
        save_config(UserConfig(ui=UiConfig(locale='weird"locale\\x', theme="default")), path)
        loaded = load_config(path)
        assert loaded.ui.locale == 'weird"locale\\x'


class TestPathsConfig:
    def test_round_trip_with_save_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "cfg.toml"
        cfg = UserConfig(
            paths=PathsConfig(
                anno1800_save_dir=r"C:\Users\u\Documents\Anno 1800\accounts\1\savegame",
                anno117_save_dir="/home/u/.steam/anno117/savegame",
            )
        )
        save_config(cfg, path)
        loaded = load_config(path)
        assert (
            loaded.paths.anno1800_save_dir
            == r"C:\Users\u\Documents\Anno 1800\accounts\1\savegame"
        )
        assert loaded.paths.anno117_save_dir == "/home/u/.steam/anno117/savegame"

    def test_unset_paths_are_commented_out(self, tmp_path: Path) -> None:
        path = tmp_path / "cfg.toml"
        save_config(UserConfig(), path)
        text = path.read_text(encoding="utf-8")
        assert "[paths]" in text
        assert "# anno1800_save_dir" in text
        assert "# anno117_save_dir" in text

    def test_partial_paths_persist(self, tmp_path: Path) -> None:
        """1800 だけ設定した場合，117 はコメントアウトのまま保存される．"""
        path = tmp_path / "cfg.toml"
        save_config(
            UserConfig(paths=PathsConfig(anno1800_save_dir="/saves/1800")),
            path,
        )
        loaded = load_config(path)
        assert loaded.paths.anno1800_save_dir == "/saves/1800"
        assert loaded.paths.anno117_save_dir is None
        text = path.read_text(encoding="utf-8")
        assert "# anno117_save_dir" in text
