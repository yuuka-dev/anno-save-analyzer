"""``trade`` sub-command (list / summary)．"""

from __future__ import annotations

import json
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from anno_save_analyzer.trade import (
    GameTitle,
    ItemDictionary,
    by_item,
    by_route,
    extract,
)
from anno_save_analyzer.trade.models import TradeEvent

trade_app = typer.Typer(help="Inspect trade activity inside a save file.")


class GameTitleArg(StrEnum):
    ANNO_117 = "anno117"
    ANNO_1800 = "anno1800"

    def to_title(self) -> GameTitle:
        return GameTitle(self.value)


class SummaryAxis(StrEnum):
    ITEM = "item"
    ROUTE = "route"


class OutputFormat(StrEnum):
    JSON = "json"
    # 以下は S-3 (Week 3) で実装予定．現状 v0.3.0 Week 1 では未対応で
    # ``NotImplementedError`` を返す．CLI 側で choice として宣言しておくのは
    # ヘルプメッセージで利用予定の値を可視化するため．
    CSV = "csv"
    HTML = "html"
    MD = "md"


def _ensure_format_supported(fmt: OutputFormat) -> None:
    if fmt is not OutputFormat.JSON:
        raise NotImplementedError(
            f"Output format '{fmt.value}' is planned for v0.3.x; use --format json for now."
        )


def _load_dictionary(title: GameTitle, locale: str) -> ItemDictionary:
    locales: tuple[str, ...] = ("en", locale) if locale != "en" else ("en",)
    return ItemDictionary.load(title, locales=locales)


def _events(save: Path, title: GameTitle, locale: str) -> Iterable[TradeEvent]:
    items = _load_dictionary(title, locale)
    return extract(save, title=title, items=items)


def _emit_json(payload: object) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@trade_app.command("list")
def list_trades(
    save: Annotated[Path, typer.Argument(help="Path to the save file.")],
    title: Annotated[
        GameTitleArg, typer.Option("--title", help="Game title.")
    ] = GameTitleArg.ANNO_117,
    locale: Annotated[str, typer.Option("--locale", help="Display locale.")] = "en",
    fmt: Annotated[
        OutputFormat, typer.Option("--format", help="Output format.")
    ] = OutputFormat.JSON,
) -> None:
    """List every TradeEvent extracted from SAVE."""
    _ensure_format_supported(fmt)
    title_v = title.to_title()
    events = list(_events(save, title_v, locale))
    payload = [
        {
            "timestamp_tick": ev.timestamp_tick,
            "item": {
                "guid": ev.item.guid,
                "name": ev.item.display_name(locale),
                "category": ev.item.category,
            },
            "amount": ev.amount,
            "total_price": ev.total_price,
            "partner": (
                {
                    "id": ev.partner.id,
                    "display_name": ev.partner.display_name,
                    "kind": ev.partner.kind,
                }
                if ev.partner
                else None
            ),
            "route_id": ev.route_id,
            "session_id": ev.session_id,
            "source_method": ev.source_method,
        }
        for ev in events
    ]
    _emit_json(payload)


@trade_app.command("summary")
def summary(
    save: Annotated[Path, typer.Argument(help="Path to the save file.")],
    by: Annotated[SummaryAxis, typer.Option("--by", help="Aggregation axis.")] = SummaryAxis.ITEM,
    title: Annotated[
        GameTitleArg, typer.Option("--title", help="Game title.")
    ] = GameTitleArg.ANNO_117,
    locale: Annotated[str, typer.Option("--locale", help="Display locale.")] = "en",
    fmt: Annotated[
        OutputFormat, typer.Option("--format", help="Output format.")
    ] = OutputFormat.JSON,
) -> None:
    """Summarise trades by item or by route."""
    _ensure_format_supported(fmt)
    title_v = title.to_title()
    events = _events(save, title_v, locale)
    if by is SummaryAxis.ITEM:
        item_rows = by_item(events)
        _emit_json(
            [
                {
                    "guid": s.item.guid,
                    "name": s.display_name(locale),
                    "category": s.item.category,
                    "bought": s.bought,
                    "sold": s.sold,
                    "net_qty": s.net_qty,
                    "net_gold": s.net_gold,
                    "event_count": s.event_count,
                    "last_seen_tick": s.last_seen_tick,
                }
                for s in item_rows
            ]
        )
        return
    route_rows = by_route(events)
    _emit_json(
        [
            {
                "route_id": s.route_id,
                "partner_kind": s.partner_kind,
                "bought": s.bought,
                "sold": s.sold,
                "net_gold": s.net_gold,
                "event_count": s.event_count,
                "last_seen_tick": s.last_seen_tick,
            }
            for s in route_rows
        ]
    )
