"""tui.state のテスト．"""

from __future__ import annotations

from pathlib import Path

from anno_save_analyzer.trade import GameTitle, Item, TradingPartner
from anno_save_analyzer.trade.aggregate import ItemSummary, RouteSummary
from anno_save_analyzer.trade.models import TradeEvent
from anno_save_analyzer.tui.state import (
    _collect_factories_by_island,
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

    def test_progress_callback_invoked_per_stage(self, tui_state) -> None:
        """``progress`` コールバック指定時に各ステージの label が通知される．"""
        from anno_save_analyzer.tui.state import load_state as ls

        stages: list[str] = []
        ls(
            tui_state.save_path,
            title=GameTitle.ANNO_117,
            locale="en",
            items=tui_state.items,
            progress=stages.append,
        )
        # 少なくとも outer / events / aggregate / islands のラベルは呼ばれる
        assert any("outer" in s for s in stages)
        assert any("events" in s for s in stages)
        assert any("aggregat" in s for s in stages)
        assert any("islands" in s for s in stages)


class TestCollectIslandsBySession:
    def test_empty_session_ids_returns_empty_dict(self) -> None:
        result = _collect_islands_by_session([], ())
        assert result == {}

    def test_maps_by_session_id_not_event_order(self, monkeypatch) -> None:
        import anno_save_analyzer.tui.state as state_mod

        monkeypatch.setattr(
            state_mod,
            "list_player_islands",
            lambda inner: (state_mod.PlayerIsland(city_name=inner.decode("utf-8")),),
        )
        result = _collect_islands_by_session([b"first", b"second"], ("1", "0"))
        assert result["1"][0].city_name == "second"
        assert result["0"][0].city_name == "first"

    def test_non_digit_session_id_returns_empty_tuple(self) -> None:
        result = _collect_islands_by_session([b"x"], ("unknown",))
        assert result == {"unknown": ()}

    def test_out_of_range_session_id_returns_empty_tuple(self) -> None:
        result = _collect_islands_by_session([b"x"], ("99",))
        assert result == {"99": ()}


class TestCollectRoutesBySession:
    def test_empty_session_ids_returns_empty_dict(self) -> None:
        assert _collect_routes_by_session([], ()) == {}

    def test_returns_tuple_per_session(self, tui_state) -> None:
        """合成 fixture は ConstructionAI を持たないため空 tuple が返る．"""
        from anno_save_analyzer.tui.state import _load_inner_sessions

        inner_payloads = _load_inner_sessions(tui_state.save_path)
        result = _collect_routes_by_session(inner_payloads, tui_state.session_ids)
        assert set(result) == set(tui_state.session_ids)
        for sid in tui_state.session_ids:
            assert result[sid] == ()

    def test_maps_by_session_id_not_event_order(self, monkeypatch) -> None:
        import anno_save_analyzer.tui.state as state_mod
        from anno_save_analyzer.trade import TradeRouteDef

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
        result = _collect_routes_by_session([b"first", b"second"], ("1", "0"))
        assert result["1"][0].ship_id == 2
        assert result["0"][0].ship_id == 1


class TestCollectFactoriesByIsland:
    def test_empty_payloads_returns_empty(self) -> None:
        assert _collect_factories_by_island([], {}) == {}

    def test_skips_aggregates_with_no_instances(self, monkeypatch) -> None:
        """instance ゼロの AreaManager は最終 dict に含めない．"""
        import anno_save_analyzer.tui.state as state_mod
        from anno_save_analyzer.trade.factories import FactoryAggregate

        monkeypatch.setattr(
            state_mod,
            "list_factory_aggregates",
            lambda inner: (FactoryAggregate(area_manager="AreaManager_999", instances=()),),
        )
        result = _collect_factories_by_island([b"x"], {})
        assert result == {}

    def test_uses_city_name_when_player_match_known(self, monkeypatch) -> None:
        """``area_manager_to_city`` に登録された AM は city_name キーで保持．"""
        import anno_save_analyzer.tui.state as state_mod
        from anno_save_analyzer.trade.factories import FactoryAggregate, FactoryInstance

        monkeypatch.setattr(
            state_mod,
            "list_factory_aggregates",
            lambda inner: (
                FactoryAggregate(
                    area_manager="AreaManager_5",
                    instances=(FactoryInstance(building_guid=100400, productivity=1.0),),
                ),
            ),
        )
        am_to_city = {"AreaManager_5": "岡山"}
        result = _collect_factories_by_island([b"x"], am_to_city)
        assert "岡山" in result
        assert "AreaManager_5" not in result

    def test_falls_back_to_area_manager_for_npc(self, monkeypatch) -> None:
        """match していない AM はそのまま AreaManager_N キーで保持．"""
        import anno_save_analyzer.tui.state as state_mod
        from anno_save_analyzer.trade.factories import FactoryAggregate, FactoryInstance

        monkeypatch.setattr(
            state_mod,
            "list_factory_aggregates",
            lambda inner: (
                FactoryAggregate(
                    area_manager="AreaManager_99",
                    instances=(FactoryInstance(building_guid=100400, productivity=0.5),),
                ),
            ),
        )
        result = _collect_factories_by_island([b"x"], {})
        assert "AreaManager_99" in result


class TestLoadInnerSessionsHelper:
    def test_reads_a8s_via_extract_inner_filedb(
        self, tmp_path: Path, tui_state, monkeypatch
    ) -> None:
        """legacy helper は extract_inner_filedb 経由 (``.a7s`` / ``.a8s``) を踏む．"""
        import anno_save_analyzer.tui.state as state_mod

        a8s = tmp_path / "fake.a8s"
        a8s.write_bytes(tui_state.save_path.read_bytes())

        called: dict[str, int] = {"n": 0}

        def fake_extract(path):
            called["n"] += 1
            return tui_state.save_path.read_bytes()

        monkeypatch.setattr(state_mod, "extract_inner_filedb", fake_extract)
        result = state_mod._load_inner_sessions(a8s)
        assert called["n"] == 1
        assert isinstance(result, list)
