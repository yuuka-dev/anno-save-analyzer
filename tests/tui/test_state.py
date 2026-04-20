"""tui.state のテスト．"""

from __future__ import annotations

from pathlib import Path

from anno_save_analyzer.trade import GameTitle, Item, TradingPartner
from anno_save_analyzer.trade.aggregate import ItemSummary, RouteSummary
from anno_save_analyzer.trade.models import TradeEvent
from anno_save_analyzer.tui.state import (
    _collect_islands_by_session,
    _collect_routes_by_session,
    build_overview,
)


def _ev(guid: int, amount: int, price: int, *, sid: str | None = "0") -> TradeEvent:
    item = Item(guid=guid, names={"en": f"Good_{guid}"})
    return TradeEvent(
        item=item,
        amount=amount,
        total_price=price,
        partner=TradingPartner(id="anon", display_name="x", kind="route"),
        session_id=sid,
        route_id="42",
    )


class TestBuildOverview:
    def test_collects_distinct_sessions_in_order(self, tmp_path: Path) -> None:
        events = [
            _ev(1, 1, 1, sid="0"),
            _ev(2, 1, 1, sid="1"),
            _ev(3, 1, 1, sid="0"),  # duplicate
            _ev(4, 1, 1, sid=None),  # session_id absent → ignored
        ]
        item_rows = (
            ItemSummary(
                item=Item(guid=1, names={}), bought=1, sold=0, net_qty=1, net_gold=1, event_count=1
            ),
        )
        route_rows = (
            RouteSummary(
                route_id="42", partner_kind="route", bought=4, sold=0, net_gold=4, event_count=4
            ),
        )
        snap = build_overview(tmp_path / "x.bin", GameTitle.ANNO_117, events, item_rows, route_rows)
        assert snap.session_ids == ("0", "1")
        assert snap.total_events == 4
        assert snap.distinct_goods == 1
        assert snap.distinct_routes == 1
        assert snap.net_gold == 4

    def test_empty_events_yields_zero_metrics(self, tmp_path: Path) -> None:
        snap = build_overview(tmp_path / "x.bin", GameTitle.ANNO_117, [], (), ())
        assert snap.session_ids == ()
        assert snap.total_events == 0
        assert snap.distinct_goods == 0
        assert snap.distinct_routes == 0
        assert snap.net_gold == 0


class TestLoadState:
    def test_loads_default_dictionary_when_items_omitted(self, tui_state) -> None:
        # tui_state fixture が items 渡してるので別 case で items=None を踏む
        from anno_save_analyzer.tui.state import load_state as ls

        save = tui_state.save_path
        new_state = ls(save, title=GameTitle.ANNO_117, locale="en")
        # 同梱辞書を読むはずなので取れる guid は同梱の 20 物資 + extracted unknown guids
        assert new_state.overview.total_events == tui_state.overview.total_events

    def test_load_state_with_ja_locale(self, tmp_path: Path, tui_state) -> None:
        from anno_save_analyzer.tui.state import load_state as ls

        save = tui_state.save_path
        ja = ls(save, title=GameTitle.ANNO_117, locale="ja")
        assert ja.locale == "ja"


class TestCollectIslandsBySession:
    def test_empty_session_ids_returns_empty_dict(self, tmp_path: Path) -> None:
        # session_ids 空なら save 読み込みすら不要
        result = _collect_islands_by_session(tmp_path / "anything.bin", ())
        assert result == {}

    def test_a8s_suffix_routes_through_extract_inner_filedb(
        self, tmp_path: Path, tui_state, monkeypatch
    ) -> None:
        """``.a8s`` 拡張子の場合 ``extract_inner_filedb`` を経由する分岐を踏む．"""
        import importlib

        state_mod = importlib.import_module("anno_save_analyzer.tui.state")

        # tui_state.save_path は ``.bin``．``.a8s`` 拡張子に rename した copy を作る
        a8s = tmp_path / "fake.a8s"
        a8s.write_bytes(tui_state.save_path.read_bytes())

        called: dict[str, int] = {"n": 0}

        def fake_extract(path):
            called["n"] += 1
            return tui_state.save_path.read_bytes()

        monkeypatch.setattr(state_mod, "extract_inner_filedb", fake_extract)
        result = _collect_islands_by_session(a8s, ("0", "1"))
        # session ごとに何かしら（空 tuple でも良い）入ってる
        assert "0" in result
        assert called["n"] == 1

    def test_maps_by_session_id_not_event_order(self, tmp_path: Path, monkeypatch) -> None:
        import anno_save_analyzer.tui.state as state_mod

        monkeypatch.setattr(state_mod, "_load_inner_sessions", lambda _: [b"first", b"second"])
        monkeypatch.setattr(
            state_mod,
            "list_player_islands",
            lambda inner: (state_mod.PlayerIsland(city_name=inner.decode("utf-8")),),
        )

        result = _collect_islands_by_session(tmp_path / "x.bin", ("1", "0"))
        assert result["1"][0].city_name == "second"
        assert result["0"][0].city_name == "first"


class TestCollectRoutesBySession:
    def test_empty_session_ids_returns_empty_dict(self, tmp_path: Path) -> None:
        assert _collect_routes_by_session(tmp_path / "anything.bin", ()) == {}

    def test_returns_tuple_per_session(self, tui_state) -> None:
        """合成 fixture は ConstructionAI を持たないため空 tuple が返る．"""
        result = _collect_routes_by_session(tui_state.save_path, tui_state.session_ids)
        assert set(result) == set(tui_state.session_ids)
        for sid in tui_state.session_ids:
            assert result[sid] == ()

    def test_maps_by_session_id_not_event_order(self, tmp_path: Path, monkeypatch) -> None:
        import anno_save_analyzer.tui.state as state_mod
        from anno_save_analyzer.trade import TradeRouteDef

        monkeypatch.setattr(state_mod, "_load_inner_sessions", lambda _: [b"first", b"second"])
        monkeypatch.setattr(
            state_mod,
            "list_trade_routes",
            lambda inner: (
                TradeRouteDef(
                    ship_id=1 if inner == b"first" else 2,
                    route_hash=0,
                    round_travel=0,
                    establish_time=0,
                    tasks=(),
                ),
            ),
        )

        result = _collect_routes_by_session(tmp_path / "x.bin", ("1", "0"))
        assert result["1"][0].ship_id == 2
        assert result["0"][0].ship_id == 1
