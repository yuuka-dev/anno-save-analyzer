"""``anno-save-analyzer state`` — save の全抽出結果を JSON に吐く．

書記長が pandas / jupyter で分析を回すための 1 本の canonical なダンプ．
内容は Overview + 島ごとの (tier_breakdown / factories / supply balance) +
全 TradeEvent．

Usage::

    anno-save-analyzer state sample_anno1800.a7s --title anno1800 --out state.json

出力は整形済 UTF-8 (日本語 raw)．
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer

from anno_save_analyzer.latest_save import resolve_save
from anno_save_analyzer.trade.balance import IslandBalance, ProductBalance
from anno_save_analyzer.trade.models import GameTitle, TradeEvent
from anno_save_analyzer.trade.population import ResidenceAggregate, TierSummary
from anno_save_analyzer.tui.i18n import Localizer
from anno_save_analyzer.tui.state import TuiState, load_state


def dump_state(  # noqa: PLR0913,B008 — CLI entrypoint．typer.Argument/Option は default で使う慣例
    save: Path | None = typer.Argument(  # noqa: B008
        None,
        help=(
            "Anno save file (.a7s / .a8s). Omit to auto-select latest save "
            "from config.toml ([paths] anno1800_save_dir / anno117_save_dir)."
        ),
    ),
    title: str = typer.Option(  # noqa: B008
        GameTitle.ANNO_1800.value,
        "--title",
        help="Game title: anno1800 / anno117",
    ),
    locale: str = typer.Option(  # noqa: B008
        "en", "--locale", help="UI locale used to resolve display names"
    ),
    out: Path = typer.Option(..., "--out", "-o", help="Output JSON file path"),  # noqa: B008
    include_events: bool = typer.Option(  # noqa: B008
        True,
        "--events/--no-events",
        help="Include full TradeEvent ledger (can be large)",
    ),
    indent: int = typer.Option(2, "--indent", help="JSON indent (0 = compact)"),  # noqa: B008
) -> None:
    """Load the save and dump a single JSON document to ``--out``．"""
    title_enum = GameTitle(title)
    resolved = resolve_save(save, title_enum)
    if resolved is None:
        field = "anno1800_save_dir" if title_enum is GameTitle.ANNO_1800 else "anno117_save_dir"
        typer.secho(
            f"ERROR: could not auto-select a save from [paths] {field}. "
            "The setting may be unset, the configured directory may not exist, "
            "or it may contain no matching .a7s/.a8s files. "
            "Either pass the save path explicitly or fix your config.toml.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)
    if save is None:
        typer.secho(f"Auto-selected latest save: {resolved}", err=True, fg=typer.colors.CYAN)
    if not resolved.is_file():
        typer.secho(f"ERROR: save file not found: {resolved}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)
    save = resolved
    state = load_state(save, title=title_enum, locale=locale)
    localizer = Localizer.load(locale)
    payload = _build_payload(state, localizer, include_events=include_events)
    text = json.dumps(payload, ensure_ascii=False, indent=indent if indent > 0 else None)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} ({len(text):,} bytes)", file=sys.stderr)


def _build_payload(
    state: TuiState, localizer: Localizer, *, include_events: bool
) -> dict[str, Any]:
    """``TuiState`` から JSON-safe な dict に整形する．

    Pydantic の ``model_dump(mode="json")`` を base に使いつつ，
    区切りがわかりやすいよう事前に島単位のマージ (balance + factories +
    tier_breakdown + session + city) を行う．
    """
    return {
        "save": str(state.save_path),
        "title": state.title.value,
        "locale": state.locale,
        "overview": _overview_dict(state),
        "islands": _islands_list(state, localizer),
        "trade_events": (
            [_event_dict(ev, state) for ev in state.events] if include_events else None
        ),
    }


def _overview_dict(state: TuiState) -> dict[str, Any]:
    snap = state.overview
    return {
        "save_path": str(snap.save_path),
        "title": snap.title.value,
        "session_ids": list(snap.session_ids),
        "total_events": snap.total_events,
        "distinct_goods": snap.distinct_goods,
        "distinct_routes": snap.distinct_routes,
        "net_gold": snap.net_gold,
    }


def _islands_list(state: TuiState, localizer: Localizer) -> list[dict[str, Any]]:
    """island 単位の集計 (residence + factory + balance) をマージした行のリスト．"""
    balance = state.balance_table
    residences: dict[str, ResidenceAggregate] = {}
    for agg in state.population_by_city.values():
        residences.setdefault(agg.area_manager, agg)

    # tui state は factory aggregates を露出してないため balance からのみ情報を
    # 取る (balance_table が None なら island list も空)．
    out: list[dict[str, Any]] = []
    if balance is None:
        return out
    for isl in balance.islands:
        city_name = state.area_manager_to_city.get(isl.area_manager) or isl.city_name
        session_key = state.area_manager_to_session_key.get(isl.area_manager)
        session_display = localizer.t(session_key) if session_key else None
        residence_agg = residences.get(isl.area_manager)
        tier_breakdown = (
            [_tier_dict(ts) for ts in residence_agg.tier_breakdown] if residence_agg else []
        )
        out.append(
            {
                "area_manager": isl.area_manager,
                "city_name": city_name,
                "is_player": city_name is not None,
                "session_key": session_key,
                "session_display": session_display,
                "resident_total": isl.resident_total,
                "residence_count": residence_agg.residence_count if residence_agg else 0,
                "avg_saturation": residence_agg.avg_saturation_mean if residence_agg else None,
                "tier_breakdown": tier_breakdown,
                "balance": _island_balance_dict(isl, state),
            }
        )
    return out


def _tier_dict(ts: TierSummary) -> dict[str, Any]:
    return {
        "tier": ts.tier,
        "residence_count": ts.residence_count,
        "resident_total": ts.resident_total,
        "avg_saturation_mean": ts.avg_saturation_mean,
    }


def _island_balance_dict(isl: IslandBalance, state: TuiState) -> dict[str, Any]:
    return {
        "products": [_product_balance_dict(p, state) for p in isl.products],
        "deficit_count": sum(1 for p in isl.products if p.is_deficit),
    }


def _product_balance_dict(p: ProductBalance, state: TuiState) -> dict[str, Any]:
    item = state.items[p.product_guid]
    return {
        "product_guid": p.product_guid,
        "name": item.display_name(state.locale) or f"Good_{p.product_guid}",
        "name_en": item.names.get("en"),
        "produced_per_minute": p.produced_per_minute,
        "consumed_per_minute": p.consumed_per_minute,
        "delta_per_minute": p.delta_per_minute,
        "is_deficit": p.is_deficit,
    }


def _event_dict(ev: TradeEvent, state: TuiState) -> dict[str, Any]:
    """TradeEvent を JSON-safe な dict に．Pydantic ``model_dump`` でも行けるが
    item を product_guid だけでなく name も添えて分析しやすくする．
    """
    item_name = ev.item.display_name(state.locale) or f"Good_{ev.item.guid}"
    return {
        "timestamp_tick": ev.timestamp_tick,
        "product_guid": ev.item.guid,
        "product_name": item_name,
        "amount": ev.amount,
        "total_price": ev.total_price,
        "session_id": ev.session_id,
        "island_name": ev.island_name,
        "route_id": ev.route_id,
        "route_name": ev.route_name,
        "partner_id": ev.partner.id if ev.partner else None,
        "partner_kind": ev.partner.kind if ev.partner else None,
        "source_method": ev.source_method,
    }


def register(app: typer.Typer) -> None:
    """Register ``state`` subcommand onto the root typer app."""
    app.command(
        name="state",
        help="Dump the full analysis state as JSON (for pandas / jupyter).",
    )(dump_state)
