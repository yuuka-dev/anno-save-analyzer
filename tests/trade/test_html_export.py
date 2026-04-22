"""trade.html_export の単体テスト．"""

from __future__ import annotations

import json
import re

from anno_save_analyzer.trade.aggregate import by_item, by_route
from anno_save_analyzer.trade.html_export import (
    build_dashboard_data,
    dashboard_to_html,
)
from anno_save_analyzer.trade.items import ItemDictionary
from anno_save_analyzer.trade.models import (
    GameTitle,
    Item,
    TradeEvent,
    TradingPartner,
)
from anno_save_analyzer.trade.storage import IslandStorageTrend, PointSeries


def _events() -> list[TradeEvent]:
    items = {1010566: Item(guid=1010566, names={"en": "Oil", "ja": "石油"})}

    def _ev(tick: int, amt: int, gold: int = 0) -> TradeEvent:
        return TradeEvent(
            timestamp_tick=tick,
            item=items[1010566],
            amount=amt,
            total_price=gold,
            session_id="0",
            island_name="Osaka",
            route_id="7",
            route_name="Osaka-Tokyo",
            partner=TradingPartner(id="route:7", display_name="Route #7", kind="route"),
            source_method="history",
        )

    return [_ev(1000, 10), _ev(2000, -5, 50), _ev(3000, 20)]


def _items_dict() -> ItemDictionary:
    return ItemDictionary({1010566: Item(guid=1010566, names={"en": "Oil", "ja": "石油"})})


def _trends() -> list[IslandStorageTrend]:
    return [
        IslandStorageTrend(
            island_name="Osaka",
            product_guid=1010566,
            points=PointSeries(capacity=3, size=3, samples=(100, 80, 60)),
        ),
    ]


class TestBuildDashboardData:
    def test_shape(self) -> None:
        events = _events()
        items = _items_dict()
        trends = _trends()
        data = build_dashboard_data(
            events=events,
            item_summaries=by_item(events),
            route_summaries=by_route(events),
            inventory_trends=trends,
            items=items,
            title=GameTitle.ANNO_1800,
            locale="ja",
            save_name="test.a7s",
        )
        assert data["meta"]["title"] == "anno1800"
        assert data["meta"]["save"] == "test.a7s"
        assert data["meta"]["locale"] == "ja"
        assert len(data["events"]) == 3
        assert data["events"][0]["item_name"] == "石油"  # ja localised
        assert any(t["island"] == "Osaka" for t in data["inventory"])
        # slope = -20/min (100→80→60), so runway_min should exist
        assert data["runways"]
        assert data["shortages"]  # 60 units at -20/min → 3 min runway → critical
        assert data["balances"][0]["net_slope_per_min"] < 0  # deficit

    def test_minutes_ago_computed(self) -> None:
        events = _events()
        data = build_dashboard_data(
            events=events,
            item_summaries=by_item(events),
            route_summaries=by_route(events),
            inventory_trends=[],
            items=_items_dict(),
            title=GameTitle.ANNO_1800,
            locale="en",
        )
        # newest event (tick=3000) should have min_ago=0.0
        min_agos = [e["min_ago"] for e in data["events"]]
        assert 0.0 in min_agos
        # all finite
        assert all(v is not None for v in min_agos)


class TestDashboardToHtml:
    def test_output_is_valid_html_with_embedded_json(self) -> None:
        events = _events()
        data = build_dashboard_data(
            events=events,
            item_summaries=by_item(events),
            route_summaries=by_route(events),
            inventory_trends=_trends(),
            items=_items_dict(),
            title=GameTitle.ANNO_1800,
            locale="ja",
            save_name="test.a7s",
        )
        out = dashboard_to_html(data)
        assert out.startswith("<!DOCTYPE html>")
        assert "<script" in out
        # 埋め込み JSON が有効
        match = re.search(
            r'<script type="application/json" id="dashboard-data">(.*?)</script>',
            out,
            re.DOTALL,
        )
        assert match is not None
        parsed = json.loads(match.group(1))
        assert parsed["meta"]["save"] == "test.a7s"

    def test_sections_present(self) -> None:
        data = build_dashboard_data(
            events=[],
            item_summaries=[],
            route_summaries=[],
            inventory_trends=[],
            items=_items_dict(),
            title=GameTitle.ANNO_117,
            locale="en",
        )
        out = dashboard_to_html(data)
        for section_id in [
            "overview",
            "shortages",
            "balance",
            "inventory",
            "items",
            "routes",
            "events",
        ]:
            assert f'id="{section_id}"' in out, f"missing section {section_id}"

    def test_save_name_escaped_in_header(self) -> None:
        """``<script>`` を save 名に突っ込んでも HTML escape される．

        header は ``html.escape`` で `&lt;` に変換．script JSON 領域でも
        ``</script>`` を ``<\\/script>`` に変換して DOM 早期終了を防ぐ．
        """
        data = build_dashboard_data(
            events=[],
            item_summaries=[],
            route_summaries=[],
            inventory_trends=[],
            items=_items_dict(),
            title=GameTitle.ANNO_1800,
            locale="en",
            save_name="<script>alert(1)</script>",
        )
        out = dashboard_to_html(data)
        # header section は html.escape されとる
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out
        # baseline は 3 個 (Plotly CDN / JSON data / inline logic) — save 名由来の
        # 余分な ``</script>`` が JSON 領域に混入したら 4 個になる．escape してるので 3．
        # template にも ``}})();\\n</script>`` が含まれるため JSON の外で 1 個増えるが
        # 悪意のある save_name 入力でこれを増やさんことを確認する．
        clean_data = build_dashboard_data(
            events=[],
            item_summaries=[],
            route_summaries=[],
            inventory_trends=[],
            items=_items_dict(),
            title=GameTitle.ANNO_1800,
            locale="en",
            save_name="normal",
        )
        clean_out = dashboard_to_html(clean_data)
        assert out.count("</script>") == clean_out.count("</script>")

    def test_embedded_json_parses_with_html_comment_tokens_in_save_name(self) -> None:
        data = build_dashboard_data(
            events=[],
            item_summaries=[],
            route_summaries=[],
            inventory_trends=[],
            items=_items_dict(),
            title=GameTitle.ANNO_1800,
            locale="en",
            save_name="before <!-- middle --> after",
        )
        out = dashboard_to_html(data)
        match = re.search(
            r'<script type="application/json" id="dashboard-data">(.*?)</script>',
            out,
            re.DOTALL,
        )
        assert match is not None
        parsed = json.loads(match.group(1))
        assert parsed["meta"]["save"] == "before <!-- middle --> after"
class TestTitleInference:
    """GameTitle.from_save_path (PR A の拡張子推定)．"""

    def test_a7s_is_anno1800(self) -> None:
        assert GameTitle.from_save_path("foo/bar.a7s") is GameTitle.ANNO_1800

    def test_a8s_is_anno117(self) -> None:
        assert GameTitle.from_save_path("/abs/baz.a8s") is GameTitle.ANNO_117

    def test_upper_case_suffix(self) -> None:
        assert GameTitle.from_save_path("BAR.A7S") is GameTitle.ANNO_1800

    def test_unknown_extension_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="Cannot infer"):
            GameTitle.from_save_path("foo.zip")
