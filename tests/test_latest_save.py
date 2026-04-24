"""``latest_save`` の save 解決 / 最新選択のテスト．

env vars ではなく ``UserConfig`` を組み立てて渡す方針．installed user の
``~/.config/anno-save-analyzer/config.toml`` ベースの解決を検証する．
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from anno_save_analyzer.config import PathsConfig, UserConfig
from anno_save_analyzer.latest_save import latest_save, resolve_save, save_dir_for
from anno_save_analyzer.trade.models import GameTitle


def _cfg(**paths: str | None) -> UserConfig:
    return UserConfig(paths=PathsConfig(**paths))


class TestSaveDirFor:
    def test_returns_path_when_config_set(self, tmp_path: Path) -> None:
        cfg = _cfg(anno1800_save_dir=str(tmp_path))
        assert save_dir_for(GameTitle.ANNO_1800, cfg=cfg) == tmp_path

    def test_returns_none_when_config_unset(self) -> None:
        cfg = _cfg()
        assert save_dir_for(GameTitle.ANNO_1800, cfg=cfg) is None

    def test_returns_none_when_config_empty_string(self) -> None:
        cfg = _cfg(anno1800_save_dir="")
        assert save_dir_for(GameTitle.ANNO_1800, cfg=cfg) is None

    def test_returns_none_when_path_missing(self, tmp_path: Path) -> None:
        cfg = _cfg(anno1800_save_dir=str(tmp_path / "does-not-exist"))
        assert save_dir_for(GameTitle.ANNO_1800, cfg=cfg) is None

    def test_anno117_uses_separate_field(self, tmp_path: Path) -> None:
        cfg = _cfg(anno117_save_dir=str(tmp_path))
        assert save_dir_for(GameTitle.ANNO_117, cfg=cfg) == tmp_path
        assert save_dir_for(GameTitle.ANNO_1800, cfg=cfg) is None

    def test_loads_default_config_when_cfg_omitted(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        # ANNO_SAVE_ANALYZER_CONFIG で config.toml を差し替え，呼び出し側が
        # ``cfg`` を渡さなくても load_config 経由で読まれることを確認．
        cfg_path = tmp_path / "config.toml"
        save_dir = tmp_path / "saves"
        save_dir.mkdir()
        cfg_path.write_text(
            f'[paths]\nanno1800_save_dir = "{save_dir}"\n', encoding="utf-8"
        )
        monkeypatch.setenv("ANNO_SAVE_ANALYZER_CONFIG", str(cfg_path))
        assert save_dir_for(GameTitle.ANNO_1800) == save_dir


class TestLatestSave:
    def test_returns_newest_mtime_a7s(self, tmp_path: Path) -> None:
        cfg = _cfg(anno1800_save_dir=str(tmp_path))
        old = tmp_path / "old.a7s"
        new = tmp_path / "new.a7s"
        old.write_bytes(b"x")
        time.sleep(0.05)
        new.write_bytes(b"y")
        assert latest_save(GameTitle.ANNO_1800, cfg=cfg) == new

    def test_ignores_other_extensions(self, tmp_path: Path) -> None:
        cfg = _cfg(anno1800_save_dir=str(tmp_path))
        (tmp_path / "decoy.txt").write_bytes(b"x")
        (tmp_path / "only.a7s").write_bytes(b"y")
        assert latest_save(GameTitle.ANNO_1800, cfg=cfg) == tmp_path / "only.a7s"

    def test_a8s_for_anno117(self, tmp_path: Path) -> None:
        cfg = _cfg(anno117_save_dir=str(tmp_path))
        (tmp_path / "wrong.a7s").write_bytes(b"x")
        (tmp_path / "right.a8s").write_bytes(b"y")
        assert latest_save(GameTitle.ANNO_117, cfg=cfg) == tmp_path / "right.a8s"

    def test_returns_none_when_no_saves(self, tmp_path: Path) -> None:
        cfg = _cfg(anno1800_save_dir=str(tmp_path))
        assert latest_save(GameTitle.ANNO_1800, cfg=cfg) is None

    def test_returns_none_when_dir_missing(self) -> None:
        cfg = _cfg()
        assert latest_save(GameTitle.ANNO_1800, cfg=cfg) is None


class TestResolveSave:
    def test_explicit_path_returned_as_is(self, tmp_path: Path) -> None:
        p = tmp_path / "mysave.a7s"
        p.write_bytes(b"x")
        assert resolve_save(p, GameTitle.ANNO_1800, cfg=_cfg()) == p

    def test_none_falls_back_to_latest(self, tmp_path: Path) -> None:
        cfg = _cfg(anno1800_save_dir=str(tmp_path))
        (tmp_path / "one.a7s").write_bytes(b"x")
        time.sleep(0.05)
        (tmp_path / "two.a7s").write_bytes(b"y")
        assert resolve_save(None, GameTitle.ANNO_1800, cfg=cfg) == tmp_path / "two.a7s"

    def test_none_returns_none_when_nothing_found(self) -> None:
        assert resolve_save(None, GameTitle.ANNO_1800, cfg=_cfg()) is None


@pytest.mark.parametrize(
    ("title", "field"),
    [
        (GameTitle.ANNO_1800, "anno1800_save_dir"),
        (GameTitle.ANNO_117, "anno117_save_dir"),
    ],
)
def test_save_dir_for_uses_title_specific_field(
    tmp_path: Path, title: GameTitle, field: str
) -> None:
    cfg = _cfg(**{field: str(tmp_path)})
    assert save_dir_for(title, cfg=cfg) == tmp_path
