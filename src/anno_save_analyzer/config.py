"""ユーザー設定の永続化 (``config.toml``)．

書記長 feedback (v0.4.2 C): ``^L`` で locale 切替，``^R`` で chart window
切替，``^P`` で直近取引窓 — これらを毎回起動時に打ち直すのは不毛．XDG 準拠
の ``~/.config/anno-save-analyzer/config.toml`` に Pydantic ベースで round-trip．

スキーマ例::

    [ui]
    locale = "ja"
    theme = "ussr"
    chart_window = "120m"
    recent_window_minutes = 120

    [paths]
    anno1800_save_dir = "C:\\Users\\<you>\\Documents\\Anno 1800\\accounts\\<id>\\savegame"
    anno117_save_dir = "C:\\Users\\<you>\\Documents\\Anno 117 - Pax Romana\\accounts\\<id>\\savegame"

- 破損 TOML / 未知キー / ファイル無しは default に倒し stderr に warning．
  CLI 起動を止めない (書記長が混乱する)．
- 環境変数 ``ANNO_SAVE_ANALYZER_CONFIG`` で完全 override (test / 1 回限りの
  起動設定に便利)．
- Windows は ``%APPDATA%\\anno-save-analyzer\\config.toml``，それ以外は
  XDG_CONFIG_HOME or ``~/.config`` ベース．
- atomic write: tmp 書いてから ``rename`` (途中電源断で破損しない)．
"""

from __future__ import annotations

import os
import sys
import tempfile
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from .trade.chart_window import ChartTimeWindow

_ENV_OVERRIDE = "ANNO_SAVE_ANALYZER_CONFIG"
_APP_NAME = "anno-save-analyzer"

# ChartTimeWindow ↔ TOML 文字列表現．書記長が手で TOML を開いても読めるよう
# "120m" / "4h" 形式．enum 追加時はここに 1 行追加する．
_CHART_WINDOW_TO_TOKEN: dict[ChartTimeWindow, str] = {
    ChartTimeWindow.LAST_120_MIN: "120m",
    ChartTimeWindow.LAST_4H: "4h",
    ChartTimeWindow.LAST_12H: "12h",
    ChartTimeWindow.LAST_24H: "24h",
    ChartTimeWindow.ALL: "all",
}
_TOKEN_TO_CHART_WINDOW: dict[str, ChartTimeWindow] = {
    v: k for k, v in _CHART_WINDOW_TO_TOKEN.items()
}


def chart_window_to_token(window: ChartTimeWindow) -> str:
    return _CHART_WINDOW_TO_TOKEN[window]


def chart_window_from_token(token: str) -> ChartTimeWindow | None:
    return _TOKEN_TO_CHART_WINDOW.get(token)


class UiConfig(BaseModel):
    """TUI / CLI 共通の UI 設定．"""

    locale: str = "en"
    theme: str = "default"
    chart_window: str = Field(default=chart_window_to_token(ChartTimeWindow.LAST_120_MIN))
    # ``^P`` 直近取引窓の分値．``None`` = 全期間．``str`` を避け数値のまま保存．
    recent_window_minutes: float | None = None

    model_config = {"frozen": True, "extra": "ignore"}


class PathsConfig(BaseModel):
    """save ディレクトリの永続化．installed (``uv tool install``) 環境では
    repo root の ``.env`` が読めないため，XDG config に置く．
    """

    anno1800_save_dir: str | None = None
    anno117_save_dir: str | None = None

    model_config = {"frozen": True, "extra": "ignore"}


class UserConfig(BaseModel):
    """書記長のユーザー設定一式．拡張は sub-section (``[section]``) 追加で．"""

    ui: UiConfig = Field(default_factory=UiConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    model_config = {"frozen": True, "extra": "ignore"}


def default_config_path() -> Path:
    """現 OS での標準 config パスを返す．``ANNO_SAVE_ANALYZER_CONFIG`` 優先．"""
    override = os.environ.get(_ENV_OVERRIDE)
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / _APP_NAME / "config.toml"
        # APPDATA 未設定 Windows は極めて稀．$HOME fallback で crash を避ける．
        return Path.home() / f".{_APP_NAME}.toml"  # pragma: no cover
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / _APP_NAME / "config.toml"


def load_config(path: Path | None = None) -> UserConfig:
    """``config.toml`` を load．不在 / 破損 / 不正型は default に倒す．

    warning は stderr に 1 行．crash させない方針．
    """
    path = path or default_config_path()
    if not path.is_file():
        return UserConfig()
    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(
            f"warning: config {path} could not be read ({exc}); using defaults",
            file=sys.stderr,
        )
        return UserConfig()
    try:
        return UserConfig.model_validate(raw)
    except ValidationError as exc:
        print(
            f"warning: config {path} has invalid fields ({exc.error_count()} errors); "
            "using defaults",
            file=sys.stderr,
        )
        return UserConfig()


def save_config(cfg: UserConfig, path: Path | None = None) -> Path | None:
    """``cfg`` を atomic に書き込む．失敗時は warning のみで ``None`` を返す．

    tmp file を同一ディレクトリに作ってから ``replace`` で rename．途中落ち
    でも既存 config が壊れない．read-only FS / 権限不足でも crash させない．
    """
    path = path or default_config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"warning: cannot create config dir {path.parent} ({exc})", file=sys.stderr)
        return None
    try:
        # tomllib には dump 機能がないので自前で整形．キー数が少ないので素直に書く．
        content = _render_toml(cfg)
        tmp_fd, tmp_path_str = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent, text=True)
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            tmp_path.replace(path)
        except OSError:
            tmp_path.unlink(missing_ok=True)
            raise
    except OSError as exc:
        print(f"warning: cannot write config {path} ({exc})", file=sys.stderr)
        return None
    return path


def _render_toml(cfg: UserConfig) -> str:
    """UserConfig を TOML 文字列にシリアライズ．手書き (tomli-w を増やさない)．"""
    ui = cfg.ui
    lines: list[str] = ["[ui]"]
    lines.append(f'locale = "{_quote(ui.locale)}"')
    lines.append(f'theme = "{_quote(ui.theme)}"')
    lines.append(f'chart_window = "{_quote(ui.chart_window)}"')
    if ui.recent_window_minutes is None:
        # 明示的に存在させておくとユーザーが TOML を開いた時に書記長の意図が明確．
        lines.append("# recent_window_minutes = 60   # コメントアウト = 全期間")
    else:
        lines.append(f"recent_window_minutes = {ui.recent_window_minutes}")

    paths = cfg.paths
    lines.append("")
    lines.append("[paths]")
    if paths.anno1800_save_dir is None:
        lines.append(
            '# anno1800_save_dir = "C:\\\\Users\\\\<you>\\\\Documents\\\\Anno 1800\\\\accounts\\\\<id>\\\\savegame"'
        )
    else:
        lines.append(f'anno1800_save_dir = "{_quote(paths.anno1800_save_dir)}"')
    if paths.anno117_save_dir is None:
        lines.append(
            '# anno117_save_dir = "C:\\\\Users\\\\<you>\\\\Documents\\\\Anno 117 - Pax Romana\\\\accounts\\\\<id>\\\\savegame"'
        )
    else:
        lines.append(f'anno117_save_dir = "{_quote(paths.anno117_save_dir)}"')
    return "\n".join(lines) + "\n"


def _quote(value: str) -> str:
    """TOML ベアストリング内で安全になるよう ``"`` と ``\\`` をエスケープ．"""
    return value.replace("\\", "\\\\").replace('"', '\\"')
