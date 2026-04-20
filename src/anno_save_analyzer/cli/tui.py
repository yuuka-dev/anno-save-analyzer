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

    # stderr にステージラベルを流すプログレス．Textual が stdout を掴むので
    # stderr 固定で書き出す．
    def _progress(stage: str) -> None:
        typer.secho(f"  … {stage}", err=True, fg=typer.colors.CYAN)

    typer.secho(f"Loading {save.name} …", err=True, bold=True)
    state = load_state(save, title=title.to_title(), locale=locale, progress=_progress)
    typer.secho("  ✓ ready", err=True, fg=typer.colors.GREEN)

    app = TradeApp(state, theme=theme.value)
    app.run()


def register(parent: typer.Typer) -> None:
    """親 Typer にトップレベル ``tui`` コマンドを登録する．

    ``add_typer`` で sub-Typer 経由にすると Argument 付き callback が
    usage error を起こすため，``command`` で直接登録する．
    """
    parent.command("tui")(_launch)
