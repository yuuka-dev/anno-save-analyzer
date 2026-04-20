"""``tui`` sub-command — launch the Textual viewer."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from anno_save_analyzer.trade.models import GameTitle


class GameTitleArg(StrEnum):
    ANNO_117 = "anno117"
    ANNO_1800 = "anno1800"

    def to_title(self) -> GameTitle:
        return GameTitle(self.value)


class ThemeArg(StrEnum):
    DEFAULT = "default"
    USSR = "ussr"


def _launch(
    save: Annotated[Path, typer.Argument(help="Save file (.a7s / .a8s).")],
    title: Annotated[
        GameTitleArg, typer.Option("--title", help="Game title.")
    ] = GameTitleArg.ANNO_117,
    locale: Annotated[str, typer.Option("--locale", help="UI locale (en / ja).")] = "en",
    theme: Annotated[
        ThemeArg, typer.Option("--theme", help="UI theme (default / ussr).")
    ] = ThemeArg.DEFAULT,
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

        state = load_state(save, title=title.to_title(), locale=locale, progress=_progress)
    typer.secho("  ✓ ready", err=True, fg=typer.colors.GREEN)

    app = TradeApp(state, theme=theme.value)
    app.run()


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
