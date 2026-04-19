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


def _launch(
    save: Annotated[Path, typer.Argument(help="Save file (.a7s / .a8s).")],
    title: Annotated[
        GameTitleArg, typer.Option("--title", help="Game title.")
    ] = GameTitleArg.ANNO_117,
    locale: Annotated[str, typer.Option("--locale", help="UI locale (en / ja).")] = "en",
) -> None:
    """Open the Textual trade-history viewer on SAVE."""
    from anno_save_analyzer.tui import TradeApp

    app = TradeApp.from_save(save, title=title.to_title(), locale=locale)
    app.run()


def register(parent: typer.Typer) -> None:
    """親 Typer にトップレベル ``tui`` コマンドを登録する．

    ``add_typer`` で sub-Typer 経由にすると Argument 付き callback が
    usage error を起こすため，``command`` で直接登録する．
    """
    parent.command("tui")(_launch)
