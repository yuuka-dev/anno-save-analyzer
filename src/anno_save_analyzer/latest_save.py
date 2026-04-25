"""``config.toml`` ベースの save ディレクトリ解決 & 最新 save 自動選択．

書記長要望 (2026-04-25):

- ``~/.config/anno-save-analyzer/config.toml`` (Win: ``%APPDATA%/...``) の
  ``[paths]`` section で ``anno1800_save_dir`` / ``anno117_save_dir`` を指定
- CLI / GUI 起動で ``save`` 引数を省略した時は ``--title`` に対応する dir の
  最新 mtime の ``.a7s`` (Anno 1800) / ``.a8s`` (Anno 117) を自動選択

XDG 準拠の user config に置くので ``uv tool install`` でも有効．repo root
``.env`` 方式は CWD 依存で installed 環境で破綻するため採用しない．
"""

from __future__ import annotations

from pathlib import Path

from .config import UserConfig, load_config
from .trade.models import GameTitle

_SUFFIX_BY_TITLE: dict[GameTitle, str] = {
    GameTitle.ANNO_1800: ".a7s",
    GameTitle.ANNO_117: ".a8s",
}


def _save_dir_field(cfg: UserConfig, title: GameTitle) -> str | None:
    if title is GameTitle.ANNO_1800:
        return cfg.paths.anno1800_save_dir
    if title is GameTitle.ANNO_117:
        return cfg.paths.anno117_save_dir
    return None  # pragma: no cover - GameTitle 増えた時の保険


def save_dir_for(title: GameTitle, cfg: UserConfig | None = None) -> Path | None:
    """指定 title の save ディレクトリを config から取得．

    未設定 or ディレクトリ非存在なら ``None`` を返す．``cfg`` を渡さなければ
    ``load_config()`` が呼ばれるが，呼び出し側が既に config を持ってるなら
    渡したほうが I/O 1 回節約できる．
    """
    cfg = cfg or load_config()
    raw = _save_dir_field(cfg, title)
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def latest_save(title: GameTitle, cfg: UserConfig | None = None) -> Path | None:
    """``save_dir_for(title)`` 配下から最新 mtime の save ファイルを返す．

    Anno 1800 → ``.a7s`` / Anno 117 → ``.a8s``．該当 dir が無い or ファイル
    0 件なら ``None``．
    """
    dir_ = save_dir_for(title, cfg=cfg)
    if dir_ is None:
        return None
    suffix = _SUFFIX_BY_TITLE[title]
    saves = list(dir_.glob(f"*{suffix}"))
    if not saves:
        return None
    return max(saves, key=lambda p: p.stat().st_mtime)


def resolve_save(save: Path | None, title: GameTitle, cfg: UserConfig | None = None) -> Path | None:
    """CLI 引数 ``save`` の解決ロジック．

    - ``save`` 明示指定 → そのまま
    - 未指定 → config の save dir から最新 save を探す
    - 見つからない → ``None`` (呼び出し側でエラー処理)
    """
    if save is not None:
        return save
    return latest_save(title, cfg=cfg)
