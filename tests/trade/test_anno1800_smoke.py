"""Anno 1800 実セーブを使った parity smoke test．

書記長の ``sample_anno1800.a7s`` を起点に，``Anno1800Interpreter`` が
``Anno117Interpreter`` 由来のロジックで実セーブを通せることを保証する．

経緯: v0.3 Week 3 で Anno 1800 完全対応が spillover (#24) のまま放置されてた．
DOM spike (2026-04-22) で以下を実測確認:

- ``TradedGoods`` の祖先 stack は Anno 117 と完全同形
  ``[..., AreaInfo, <1>, PassiveTrade, History, {TradeRouteEntries|PassiveTradeEntries}, <1>, <1>, TradedGoods]``
- ``GoodGuid`` / ``GoodAmount`` / ``TotalPrice`` の attrib 名・layout も同一
- ``TotalPrice`` は sparse (実測 4856 中 219 = 4.5%)．これは仕様で，
  自国島間ルート輸送には gold 発生せず NPC 取引のみ price が付く

CI など実セーブが無い環境では ``SAMPLE_ANNO1800`` env で path を override
できる．無ければ skip．
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

import pytest

from anno_save_analyzer.trade.extract import extract
from anno_save_analyzer.trade.interpreter import (
    Anno117Interpreter,
    Anno1800Interpreter,
    select_interpreter,
)
from anno_save_analyzer.trade.items import ItemDictionary
from anno_save_analyzer.trade.models import GameTitle

_DEFAULT_SAMPLE = Path(__file__).resolve().parents[2] / "sample_anno1800.a7s"
SAMPLE_PATH = Path(os.environ.get("SAMPLE_ANNO1800", _DEFAULT_SAMPLE))
_HAS_SAMPLE = SAMPLE_PATH.is_file()


class TestAnno1800InterpreterDispatch:
    """Anno1800Interpreter が登録されとるか / 117 の継承であることを明示．"""

    def test_select_interpreter_returns_anno1800(self) -> None:
        interp = select_interpreter(GameTitle.ANNO_1800)
        assert isinstance(interp, Anno1800Interpreter)

    def test_anno1800_inherits_anno117_logic(self) -> None:
        """DOM 同形なので継承で動く．差分が必要になったら独立実装に剥がす．"""
        assert issubclass(Anno1800Interpreter, Anno117Interpreter)
        assert Anno1800Interpreter().title is GameTitle.ANNO_1800


@pytest.mark.skipif(not _HAS_SAMPLE, reason=f"Anno 1800 sample not found: {SAMPLE_PATH}")
class TestAnno1800RealSampleExtraction:
    """``sample_anno1800.a7s`` の実セーブから抽出が end-to-end で通る．"""

    @pytest.fixture(scope="class")
    def events(self) -> list:
        items = ItemDictionary.load(GameTitle.ANNO_1800, locales=("en",))
        return list(extract(SAMPLE_PATH, title=GameTitle.ANNO_1800, items=items))

    def test_extracts_nontrivial_event_count(self, events: list) -> None:
        # 実測 8852．DLC が増えても 1000 は下回らない想定の floor．
        assert len(events) >= 1000

    def test_partner_kinds_are_classified(self, events: list) -> None:
        """全 event の partner は classify 済 ('route' / 'passive') か None．

        None は ``Trader`` attrib 欠落で id 取れんかったケース．許容するが
        kind=='unknown' な partner が残っとったら interpreter のバグ．
        """
        kinds = Counter(e.partner.kind if e.partner else None for e in events)
        assert "unknown" not in kinds, f"unexpected kind=='unknown': {kinds}"
        # route / passive のいずれかが必ず populate されとる
        assert kinds.get("route", 0) > 0 or kinds.get("passive", 0) > 0

    def test_multiple_sessions_populated(self, events: list) -> None:
        """少なくとも 2 セッション以上から event が出る．Old World 単独で
        終わっとるセーブはほぼ無い (DLC 解放後の典型は 3 以上)．"""
        sessions = {e.session_id for e in events}
        assert len(sessions) >= 2

    def test_island_names_are_decoded_strings(self, events: list) -> None:
        """``CityName`` の UTF-16LE decode が機能しとる．null padding や
        U+200B が混入しとったら test_zero_width_space_and_padding_stripped
        相当の処理が効いてないということ．"""
        names = {e.island_name for e in events if e.island_name}
        assert names, "no island names extracted at all"
        for n in names:
            assert "\x00" not in n, f"null byte leaked into island name: {n!r}"
            assert "\u200b" not in n, f"ZWSP not stripped from island name: {n!r}"

    def test_item_guid_range_matches_anno1800(self, events: list) -> None:
        """Anno 1800 の Product GUID は概ね 1010xxx 帯 + 旧式の小さい id 帯
        (例: 535, 2524) が混在する．少なくとも 1010000 以上のアイテムが
        含まれることを確認 (Anno 117 の主要 GUID が 1010xxx 帯)．"""
        guids = {e.item.guid for e in events}
        assert any(g >= 1010000 for g in guids), f"no high-range GUIDs found: {sorted(guids)[:10]}"

    def test_timestamp_ticks_populated(self, events: list) -> None:
        """``ExecutionTime`` attrib が拾えとる．timestamp_tick=None ばかり
        だったら interpreter が attrib をとってきてない (Anno 117 と同名と
        判明済なので落ちるはずがない)．"""
        with_ts = sum(1 for e in events if e.timestamp_tick is not None)
        assert with_ts > 0
        # 実測ほぼ 100% (ExecutionTime は Anno 1800 でも 2817/2817 で 100%)
        assert with_ts / len(events) > 0.9

    def test_some_events_have_nonzero_total_price(self, events: list) -> None:
        """NPC 売却分は ``TotalPrice`` が付く．自国島間ルートは 0 が正しい．
        全件 0 になっとったら interpreter が attrib を見逃しとる．"""
        priced = [e for e in events if e.total_price]
        assert priced, "no events with total_price > 0 (interpreter likely missing TotalPrice)"

    def test_route_kind_carries_route_id(self, events: list) -> None:
        """route partner には route_id が必ず attached．"""
        route_events = [e for e in events if e.partner and e.partner.kind == "route"]
        if route_events:
            assert all(e.route_id is not None for e in route_events)
