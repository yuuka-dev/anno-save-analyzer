"""Top-level CLI entry．サブコマンドを束ねる．"""

from __future__ import annotations

import typer

from .trade import trade_app

app = typer.Typer(
    name="anno-save-analyzer",
    help="Trade history extraction for Anno 117 / Anno 1800 saves.",
    no_args_is_help=True,
)
app.add_typer(trade_app, name="trade")


if __name__ == "__main__":  # pragma: no cover
    app()
