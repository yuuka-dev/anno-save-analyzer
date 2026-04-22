"""``tui`` sub-command — launch the Textual viewer."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from anno_save_analyzer.cli._title import resolve_title
from anno_save_analyzer.trade.models import GameTitle


class GameTitleArg(StrEnum):
    ANNO_117 = "anno117"
    ANNO_1800 = "anno1800"

    def to_title(self) -> GameTitle:
        return GameTitle(self.value)


_LOCALE_SENTINEL = "__from_config__"
_THEME_SENTINEL = "__from_config__"


def _launch(
    save: Annotated[Path, typer.Argument(help="Save file (.a7s / .a8s).")],
    title: Annotated[
        GameTitleArg | None,
        typer.Option(
            "--title", help="Game title. Defaults to extension: .a7s=anno1800 / .a8s=anno117."
        ),
    ] = None,
    locale: Annotated[
        str,
        typer.Option(
            "--locale",
            help="UI locale (en / ja). Defaults to saved config value.",
        ),
    ] = _LOCALE_SENTINEL,
    theme: Annotated[
        str,
        typer.Option(
            "--theme",
            help="UI theme (default / ussr). Defaults to saved config value.",
        ),
    ] = _THEME_SENTINEL,
) -> None:
    """Open the Textual trade-history viewer on SAVE.

    Long saves may take 10–40 seconds to parse; a progress log is printed to
    stderr while loading.
    """
    try:
        from anno_save_analyzer.tui import TradeApp
        from anno_save_analyzer.tui.state import load_state
    except ImportError as exc:
        typer.secho(
            "The TUI dependencies are not installed. Install "
            "'anno-save-analyzer[tui]' (or the equivalent optional extras) "
            "and try again.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1) from exc

    # 設定ファイルを先に読んで CLI 引数と merge．CLI 指定があればそちらを優先．
    from anno_save_analyzer.config import (
        chart_window_from_token,
        load_config,
    )

    user_cfg = load_config()
    resolved_locale = locale if locale != _LOCALE_SENTINEL else user_cfg.ui.locale
    resolved_theme = theme if theme != _THEME_SENTINEL else user_cfg.ui.theme
    if resolved_theme not in ("default", "ussr"):
        typer.secho(
            f"warning: unknown theme {resolved_theme!r} in config; falling back to 'default'",
            err=True,
            fg=typer.colors.YELLOW,
        )
        resolved_theme = "default"
    saved_chart_window = chart_window_from_token(user_cfg.ui.chart_window)
    locale = resolved_locale
    theme_value = resolved_theme
    recent_window = user_cfg.ui.recent_window_minutes

    # 進捗ゲージ (stderr)．Textual を起動すると stdout を掴むため err=True 固定．
    # ``load_state`` は各ステージ開始時に progress(stage_label) を呼び，
    # ゲージはステージ粒度 (1/5, 2/5, …) で正直に進む．
    # データ量に比例した細かいゲージは v0.4 以降で検討 (各ステージ内で
    # chunk progress を報告する設計変更が必要)．
    stage_total = 5
    typer.secho(f"Loading {save.name} …", err=True, bold=True)
    with typer.progressbar(
        length=stage_total,
        label="  starting",
        file=_stderr(),
        fill_char="█",
        empty_char="░",
        show_eta=False,
        show_percent=True,
    ) as bar:
        step = 0

        def _progress(stage: str) -> None:
            nonlocal step
            step += 1
            bar.label = f"  [{step}/{stage_total}] {stage}"
            bar.update(1)

        resolved_title = resolve_title(save, title.to_title() if title is not None else None)
        state = load_state(save, title=resolved_title, locale=locale, progress=_progress)
    typer.secho("  ✓ ready", err=True, fg=typer.colors.GREEN)

    app = TradeApp(state, theme=theme_value, persist_settings=True)
    # ``^R`` / ``^P`` の初期値も config から復元．TradeApp init は statistics 画面を
    # まだ install していないため，mount 後に設定する．
    _apply_saved_stat_settings(app, saved_chart_window, recent_window)
    app.run()


def _apply_saved_stat_settings(app, chart_window, recent_window_minutes) -> None:
    """起動後 statistics 画面の config 値を復元する．install_screen は on_mount で
    行われるので，ここでは mount 時フックを立てて差し替える．
    """
    original_on_mount = app.on_mount

    def on_mount_then_restore() -> None:
        original_on_mount()
        try:
            stats = app.get_screen("statistics")
        except KeyError:  # pragma: no cover - install_screen 成功前提
            return
        if chart_window is not None:
            stats._chart_window = chart_window
        stats._recent_window_minutes = recent_window_minutes

    app.on_mount = on_mount_then_restore  # type: ignore[method-assign]


def _stderr():
    """``typer.progressbar`` に渡す stderr stream．小さな helper で test 容易化．"""
    import sys

    return sys.stderr


def register(parent: typer.Typer) -> None:
    """親 Typer にトップレベル ``tui`` コマンドを登録する．

    ``add_typer`` で sub-Typer 経由にすると Argument 付き callback が
    usage error を起こすため，``command`` で直接登録する．
    """
    parent.command("tui")(_launch)
