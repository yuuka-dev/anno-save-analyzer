"""Anno117Interpreter のテスト．

合成 FileDB（PassiveTrade > History > {TradeRouteEntries, PassiveTradeEntries}
階層）を作り，期待 triple が yield されることを検証する．
"""

from __future__ import annotations

import struct

from anno_save_analyzer.parser.filedb import (
    detect_version,
    parse_tag_section,
)
from anno_save_analyzer.trade.interpreter import (
    Anno117Interpreter,
    select_interpreter,
)
from anno_save_analyzer.trade.interpreter.anno117 import (
    _classify_parent,
    _read_int32,
    _read_int64,
)
from anno_save_analyzer.trade.models import GameTitle

from .conftest import make_inner_filedb, wrap_as_outer


class TestSelectInterpreter:
    def test_returns_anno117_for_anno117(self) -> None:
        interp = select_interpreter(GameTitle.ANNO_117)
        assert isinstance(interp, Anno117Interpreter)

    def test_returns_anno1800_for_anno1800(self) -> None:
        from anno_save_analyzer.trade.interpreter import Anno1800Interpreter

        interp = select_interpreter(GameTitle.ANNO_1800)
        assert isinstance(interp, Anno1800Interpreter)


class TestAnno117ExtractionFromSyntheticDOM:
    def test_route_kind_assigns_route_id_only(self) -> None:
        inner = make_inner_filedb(
            {"route": [(41, 2088, 5, 0), (41, 2073, -2, 0)]},
        )
        outer = wrap_as_outer([inner])
        section = parse_tag_section(outer, detect_version(outer))
        triples = list(Anno117Interpreter().find_traded_goods(outer, section))
        assert len(triples) == 2
        for t in triples:
            assert t.context.partner_kind == "route"
            assert t.context.route_id == "41"
            assert t.context.partner_id is None

    def test_passive_kind_assigns_partner_id_only(self) -> None:
        inner = make_inner_filedb(
            {"passive": [(32777, 2142, -3, 156)]},
        )
        outer = wrap_as_outer([inner])
        section = parse_tag_section(outer, detect_version(outer))
        triples = list(Anno117Interpreter().find_traded_goods(outer, section))
        assert len(triples) == 1
        t = triples[0]
        assert t.context.partner_kind == "passive"
        assert t.context.partner_id == "32777"
        assert t.context.route_id is None

    def test_both_kinds_in_one_session(self) -> None:
        inner = make_inner_filedb(
            {
                "route": [(10, 2088, 5, 0)],
                "passive": [(20, 2138, 3, -50)],
            }
        )
        outer = wrap_as_outer([inner])
        section = parse_tag_section(outer, detect_version(outer))
        triples = list(Anno117Interpreter().find_traded_goods(outer, section))
        kinds = sorted(t.context.partner_kind for t in triples)
        assert kinds == ["passive", "route"]

    def test_session_id_reflects_session_index(self) -> None:
        inner_a = make_inner_filedb({"route": [(1, 100, 1, 1)]})
        inner_b = make_inner_filedb({"passive": [(2, 200, 1, 1)]})
        outer = wrap_as_outer([inner_a, inner_b])
        section = parse_tag_section(outer, detect_version(outer))
        triples = list(Anno117Interpreter().find_traded_goods(outer, section))
        sessions = sorted({t.context.session_id for t in triples})
        assert sessions == ["0", "1"]

    def test_empty_session_skipped(self) -> None:
        # 空 BinaryData も含むケース
        inner_real = make_inner_filedb({"route": [(1, 100, 1, 1)]})
        outer = wrap_as_outer([inner_real, b""])
        section = parse_tag_section(outer, detect_version(outer))
        triples = list(Anno117Interpreter().find_traded_goods(outer, section))
        assert len(triples) == 1


class TestClassifyParentDirect:
    def test_too_short_stack_returns_none(self) -> None:
        assert _classify_parent(["A", "B", "C"]) is None

    def test_unrecognised_chain_returns_none(self) -> None:
        stack = ["A", "B", "C", "D", "E", "TradedGoods"]
        assert _classify_parent(stack) is None

    def test_route_chain_recognised(self) -> None:
        stack = ["X", "PassiveTrade", "History", "TradeRouteEntries", "<1>", "<1>", "TradedGoods"]
        assert _classify_parent(stack) == "route"

    def test_passive_chain_recognised(self) -> None:
        stack = ["X", "PassiveTrade", "History", "PassiveTradeEntries", "<1>", "<1>", "TradedGoods"]
        assert _classify_parent(stack) == "passive"


class TestReadHelpers:
    def test_read_int32_handles_short_buffer(self) -> None:
        assert _read_int32(b"") == 0
        assert _read_int32(b"\x01\x00\x00\x00") == 1

    def test_read_int64_handles_short_buffer(self) -> None:
        assert _read_int64(b"\x00") == 0
        assert _read_int64(struct.pack("<q", 1234567890123)) == 1234567890123


class TestFirstAttribHelpers:
    """``_first_int32_attrib`` と ``_first_int_attrib`` の網羅テスト．"""

    def test_first_int32_returns_value_when_found(self) -> None:
        from anno_save_analyzer.trade.interpreter.anno117 import _first_int32_attrib

        stack = [{"unrelated": b"\x00"}, {"Trader": struct.pack("<i", 99)}]
        assert _first_int32_attrib(stack, ("Trader",)) == 99

    def test_first_int32_short_buffer_skipped(self) -> None:
        from anno_save_analyzer.trade.interpreter.anno117 import _first_int32_attrib

        stack = [{"Trader": b"\x01"}]
        # 4 バイト未満は採用せず None
        assert _first_int32_attrib(stack, ("Trader",)) is None

    def test_first_int32_returns_none_when_no_candidate_match(self) -> None:
        from anno_save_analyzer.trade.interpreter.anno117 import _first_int32_attrib

        stack = [{"X": struct.pack("<i", 1)}]
        assert _first_int32_attrib(stack, ("Trader",)) is None

    def test_first_int_attrib_uint64_path(self) -> None:
        from anno_save_analyzer.trade.interpreter.anno117 import _first_int_attrib

        stack = [{"Tick": struct.pack("<q", 0xABCDEF)}]
        assert _first_int_attrib(stack, ("Tick",)) == 0xABCDEF

    def test_first_int_attrib_int32_fallback(self) -> None:
        from anno_save_analyzer.trade.interpreter.anno117 import _first_int_attrib

        stack = [{"Tick": struct.pack("<i", 12345)}]
        assert _first_int_attrib(stack, ("Tick",)) == 12345

    def test_first_int_attrib_unsupported_length_returns_none(self) -> None:
        from anno_save_analyzer.trade.interpreter.anno117 import _first_int_attrib

        stack = [{"Tick": b"\x00\x01\x02"}]  # 3 byte，どちらにも該当せず
        assert _first_int_attrib(stack, ("Tick",)) is None

    def test_first_int_attrib_no_match(self) -> None:
        from anno_save_analyzer.trade.interpreter.anno117 import _first_int_attrib

        assert _first_int_attrib([{"X": b"\x00\x00\x00\x00"}], ("Tick",)) is None


class TestBuildTripleEdgeCases:
    """``_build_triple_if_complete`` の枝網羅．"""

    def test_returns_none_when_good_guid_missing(self) -> None:
        from anno_save_analyzer.trade.interpreter.anno117 import (
            _build_triple_if_complete,
        )

        triple = {"good_guid": None, "amount": 5, "total_price": 10}
        assert (
            _build_triple_if_complete(triple, session_id="0", kind="route", ancestor_attribs=[])
            is None
        )

    def test_returns_none_when_amount_missing(self) -> None:
        from anno_save_analyzer.trade.interpreter.anno117 import (
            _build_triple_if_complete,
        )

        triple = {"good_guid": 100, "amount": None, "total_price": 10}
        assert (
            _build_triple_if_complete(triple, session_id="0", kind="route", ancestor_attribs=[])
            is None
        )

    def test_total_price_defaults_to_zero_when_none(self) -> None:
        from anno_save_analyzer.trade.interpreter.anno117 import (
            _build_triple_if_complete,
        )

        triple = {"good_guid": 100, "amount": 1, "total_price": None}
        result = _build_triple_if_complete(
            triple, session_id="0", kind="route", ancestor_attribs=[]
        )
        assert result is not None
        assert result.total_price == 0

    def test_unknown_kind_does_not_assign_route_or_partner(self) -> None:
        from anno_save_analyzer.trade.interpreter.anno117 import (
            _build_triple_if_complete,
        )

        triple = {"good_guid": 1, "amount": 1, "total_price": 1}
        result = _build_triple_if_complete(
            triple,
            session_id="0",
            kind="unknown",
            ancestor_attribs=[{"Trader": struct.pack("<i", 99)}],
        )
        assert result is not None
        assert result.context.route_id is None
        assert result.context.partner_id is None


class TestInTradedGoodsAttrFiltering:
    """TradedGoods 内部で GoodGuid/Amount/Price 以外の attrib が来ても無視される．"""

    def test_unknown_attribute_inside_traded_goods_ignored(self) -> None:
        from tests.parser.filedb.conftest import minimal_v3

        # AreaInfo > <1> (CityName 持ち = プレイヤー島) > PassiveTrade > History
        # > PassiveTradeEntries > <1> > <1> > TradedGoods > <1> with
        # ExtraJunk + GoodGuid + GoodAmount
        tags = {
            2: "PassiveTrade",
            3: "History",
            4: "PassiveTradeEntries",
            5: "TradedGoods",
            7: "AreaInfo",
        }
        attribs = {
            0x8001: "GoodGuid",
            0x8002: "GoodAmount",
            0x8003: "ExtraJunk",  # 関係ない attrib．無視されるはず
            0x8004: "TotalPrice",
            0x8005: "CityName",
        }
        events = [
            ("T", 7),  # AreaInfo
            ("T", 1),  # AreaInfo > <1> (player island)
            ("A", 0x8005, "島".encode("utf-16-le")),
            ("T", 2),  # PassiveTrade
            ("T", 3),  # History
            ("T", 4),  # PassiveTradeEntries
            ("T", 1),  # 外側 <1>
            ("T", 1),  # 内側 <1>
            ("T", 5),  # TradedGoods
            ("T", 1),
            ("A", 0x8003, b"\xde\xad\xbe\xef"),  # ExtraJunk → ignored branch
            ("A", 0x8001, struct.pack("<i", 100)),
            ("A", 0x8002, struct.pack("<i", 5)),
            ("X",),
            ("X",),  # close TradedGoods
            ("X",),  # close inner <1>
            ("X",),  # close outer <1>
            ("X",),  # close PassiveTradeEntries
            ("X",),  # close History
            ("X",),  # close PassiveTrade
            ("X",),  # close AreaInfo > <1>
            ("X",),  # close AreaInfo
        ]
        inner = minimal_v3(tags=tags, attribs=attribs, events=events)
        outer = wrap_as_outer([inner])
        section = parse_tag_section(outer, detect_version(outer))
        triples = list(Anno117Interpreter().find_traded_goods(outer, section))
        assert len(triples) == 1
        assert triples[0].good_guid == 100
        assert triples[0].amount == 5
        # TotalPrice 無しでも total_price=0 で組み立てる
        assert triples[0].total_price == 0


class TestNestedTagsInsideTradedGoods:
    """TradedGoods 内部に複数階層の wrapper があっても，1 階層目の close 時にだけ
    build & yield が走る (depth tracking の網羅)．"""

    def test_nested_wrapper_only_yields_at_depth_one(self) -> None:
        from tests.parser.filedb.conftest import minimal_v3

        tags = {
            2: "PassiveTrade",
            3: "History",
            4: "TradeRouteEntries",
            5: "TradedGoods",
            7: "AreaInfo",
        }
        attribs = {
            0x8001: "RouteID",
            0x8002: "GoodGuid",
            0x8003: "GoodAmount",
            0x8005: "CityName",
        }
        events = [
            ("T", 7),  # AreaInfo
            ("T", 1),  # AreaInfo > <1> (player)
            ("A", 0x8005, "島".encode("utf-16-le")),
            ("T", 2),  # PassiveTrade
            ("T", 3),  # History
            ("T", 4),  # TradeRouteEntries
            ("T", 1),  # 外側 <1>
            ("T", 1),  # 内側 <1> (entry)
            ("A", 0x8001, struct.pack("<i", 7)),  # RouteID=7 (on inner entry)
            ("T", 5),  # TradedGoods
            ("T", 1),  # depth=1 wrapper
            ("T", 1),  # depth=2 nested wrapper
            ("A", 0x8002, struct.pack("<i", 555)),  # GoodGuid
            ("A", 0x8003, struct.pack("<i", 3)),  # GoodAmount
            ("X",),  # close depth=2 wrapper
            ("X",),  # close depth=1 wrapper (build & yield)
            ("X",),  # close TradedGoods
            ("X",),  # close inner <1> (entry)
            ("X",),  # close outer <1>
            ("X",),  # close TradeRouteEntries
            ("X",),  # close History
            ("X",),  # close PassiveTrade
            ("X",),  # close AreaInfo > <1>
            ("X",),  # close AreaInfo
        ]
        inner = minimal_v3(tags=tags, attribs=attribs, events=events)
        outer = wrap_as_outer([inner])
        section = parse_tag_section(outer, detect_version(outer))
        triples = list(Anno117Interpreter().find_traded_goods(outer, section))
        assert len(triples) == 1
        assert triples[0].good_guid == 555
        assert triples[0].amount == 3
        assert triples[0].context.route_id == "7"


class TestInnerWrapperWithoutTripleYieldsNothing:
    """TradedGoods 直下 <1> が空 (good_guid 未設定) → triple is None → yield されない
    (135->137 の False 枝)．"""

    def test_empty_inner_wrapper_skipped(self) -> None:
        from tests.parser.filedb.conftest import minimal_v3

        tags = {
            2: "PassiveTrade",
            3: "History",
            4: "TradeRouteEntries",
            5: "TradedGoods",
            6: "AreaInfo",
        }
        attribs: dict[int, str] = {0x8001: "Trader", 0x8002: "CityName"}
        events = [
            ("T", 6),  # AreaInfo
            ("T", 1),  # AreaInfo > <1> (player island)
            ("A", 0x8002, "プレイヤー島".encode("utf-16-le")),
            ("T", 2),
            ("T", 3),
            ("T", 4),
            ("T", 1),  # 外側 <1>
            ("A", 0x8001, struct.pack("<i", 1)),
            ("T", 1),  # 内側 <1>
            ("T", 5),  # TradedGoods
            ("T", 1),  # depth=1 wrapper (空)
            ("X",),  # close depth=1 wrapper → build → None → yield スキップ (174->176)
            ("X",),  # close TradedGoods
            ("X",),  # close inner <1>
            ("X",),  # close outer <1>
            ("X",),  # close TradeRouteEntries
            ("X",),  # close History
            ("X",),  # close PassiveTrade
            ("X",),  # close AreaInfo > <1>
            ("X",),  # close AreaInfo
        ]
        inner = minimal_v3(tags=tags, attribs=attribs, events=events)
        outer = wrap_as_outer([inner])
        section = parse_tag_section(outer, detect_version(outer))
        triples = list(Anno117Interpreter().find_traded_goods(outer, section))
        assert triples == []


class TestNpcIslandFiltering:
    """CityName 持たない AreaInfo > <1>（NPC 島）の TradedGoods は yield されない．"""

    def test_npc_island_trades_are_excluded(self) -> None:
        from .conftest import make_inner_filedb, wrap_as_outer

        # プレイヤー島 1 件 + NPC 島 1 件．それぞれ同じ trade 構造を持つ．
        # interpreter はプレイヤー島の取引のみ拾うべき．
        inner = make_inner_filedb(
            {"route": [(7, 100, 5, 0), (7, 200, -3, 0)]},
            include_npc_island=True,
        )
        outer = wrap_as_outer([inner])
        section = parse_tag_section(outer, detect_version(outer))
        triples = list(Anno117Interpreter().find_traded_goods(outer, section))
        # プレイヤー島の 2 取引のみ．NPC 島の同じ 2 取引は skip．
        assert len(triples) == 2


class TestIslandNameAttachment:
    """#29 Phase 1: AreaInfo entry の CityName が ExtractionContext.island_name に載る．"""

    def test_island_name_populated_on_raw_triples(self) -> None:
        from .conftest import make_inner_filedb, wrap_as_outer

        inner = make_inner_filedb({"route": [(7, 100, 5, 0), (7, 200, -3, 0)]})
        outer = wrap_as_outer([inner])
        section = parse_tag_section(outer, detect_version(outer))
        triples = list(Anno117Interpreter().find_traded_goods(outer, section))
        # fixture の CityName は "プレイヤー島" 固定
        assert {t.context.island_name for t in triples} == {"プレイヤー島"}

    def test_zero_width_space_and_padding_stripped(self) -> None:
        """CityName に U+200B が混ざる実セーブケース → strip される．"""
        import struct

        from tests.parser.filedb.conftest import minimal_v3

        tags = {
            2: "PassiveTrade",
            3: "History",
            4: "TradeRouteEntries",
            5: "TradedGoods",
            6: "AreaInfo",
        }
        attribs = {
            0x8001: "RouteID",
            0x8002: "GoodGuid",
            0x8003: "GoodAmount",
            0x8004: "TotalPrice",
            0x8005: "CityName",
        }
        events = [
            ("T", 6),  # AreaInfo
            ("T", 1),  # entry
            ("A", 0x8005, "\u200bスターリングラード".encode("utf-16-le")),
            ("T", 2),
            ("T", 3),
            ("T", 4),
            ("T", 1),  # outer <1>
            ("T", 1),  # inner <1>
            ("A", 0x8001, struct.pack("<i", 42)),
            ("T", 5),
            ("T", 1),
            ("A", 0x8002, struct.pack("<i", 100)),
            ("A", 0x8003, struct.pack("<i", 1)),
            ("X",),
            ("X",),  # close TradedGoods
            ("X",),  # inner <1>
            ("X",),  # outer <1>
            ("X",),  # TradeRouteEntries
            ("X",),  # History
            ("X",),  # PassiveTrade
            ("X",),  # AreaInfo > <1>
            ("X",),  # AreaInfo
        ]
        inner = minimal_v3(tags=tags, attribs=attribs, events=events)
        outer = wrap_as_outer([inner])
        section = parse_tag_section(outer, detect_version(outer))
        triples = list(Anno117Interpreter().find_traded_goods(outer, section))
        assert len(triples) == 1
        assert triples[0].context.island_name == "スターリングラード"


class TestRootLevelAttribsAndTerminators:
    """外側 FileDB の root レベルに attrib / 余分 terminator がある DOM を扱える．"""

    def test_root_attrib_is_silently_absorbed(self) -> None:
        """tag_stack 空状態で attrib が来ても crash しない（109->112 False 枝）．"""
        from tests.parser.filedb.conftest import minimal_v3

        # root 直下に attrib + 通常 tag．`SessionFileVersion` 風の構造．
        inner = minimal_v3(
            tags={2: "OtherTag"},
            attribs={0x8001: "RootAttrib"},
            events=[
                ("A", 0x8001, struct.pack("<i", 1)),  # tag 開く前 → attrib_stack 空
                ("T", 2),
                ("X",),
            ],
        )
        outer = wrap_as_outer([inner])
        section = parse_tag_section(outer, detect_version(outer))
        triples = list(Anno117Interpreter().find_traded_goods(outer, section))
        assert triples == []

    def test_redundant_root_terminator_skipped(self) -> None:
        """iter_dom が DOM 終端で余分 terminator を 1 つだけ吐くケース．
        tag_stack 空で Terminator が来ても落ちず ``continue`` する．"""
        from tests.parser.filedb.conftest import minimal_v3

        # 1 個 terminator (root より上) — iter_dom の depth=-1 までは許容．
        inner = minimal_v3(tags={}, attribs={}, events=[("X",)])
        outer = wrap_as_outer([inner])
        section = parse_tag_section(outer, detect_version(outer))
        triples = list(Anno117Interpreter().find_traded_goods(outer, section))
        assert triples == []


class TestEmptyTradedGoodsYieldsNothing:
    """TradedGoods open → 中身 attrib 無し → close で triple 不完全のため yield されない．"""

    def test_empty_traded_goods_skipped(self) -> None:
        from tests.parser.filedb.conftest import minimal_v3

        tags = {
            2: "PassiveTrade",
            3: "History",
            4: "PassiveTradeEntries",
            5: "TradedGoods",
        }
        attribs: dict[int, str] = {}  # 何も使わない
        events = [
            ("T", 2),  # PassiveTrade
            ("T", 3),  # History
            ("T", 4),  # PassiveTradeEntries
            ("T", 1),  # 外側 <1>
            ("T", 1),  # 内側 <1>
            ("T", 5),  # TradedGoods（空）
            ("X",),  # close TradedGoods
            ("X",),  # close inner <1>
            ("X",),  # close outer <1>
            ("X",),  # close PassiveTradeEntries
            ("X",),  # close History
            ("X",),  # close PassiveTrade
        ]
        inner = minimal_v3(tags=tags, attribs=attribs, events=events)
        outer = wrap_as_outer([inner])
        section = parse_tag_section(outer, detect_version(outer))
        triples = list(Anno117Interpreter().find_traded_goods(outer, section))
        assert triples == []


class TestInterpreterIgnoresInvalidParents:
    """ConstructionAI/EventBuffer 等の想定外の親は skip される．"""

    def test_unknown_chain_skipped(self) -> None:
        """trader 無し、無効な親階層（PassiveTrade > History 配下じゃない）の TradedGoods は無視．"""
        from tests.parser.filedb.conftest import minimal_v3

        # SessionData > BinaryData(inner) という構造で，inner は GameObject > objects > <1>
        # > ConstructionAI > EventBuffer > TradedGoods という invalid path を作る．
        inner_tags = {
            2: "GameObject",
            3: "objects",
            4: "ConstructionAI",
            5: "EventBuffer",
            6: "TradedGoods",
        }
        inner_attribs = {0x8001: "GoodGuid", 0x8002: "GoodAmount"}
        events = [
            ("T", 2),
            ("T", 3),
            ("T", 1),
            ("T", 4),
            ("T", 5),
            ("T", 6),
            ("T", 1),
            ("A", 0x8001, struct.pack("<i", 100)),
            ("A", 0x8002, struct.pack("<i", 1)),
            ("X",),  # close inner <1>
            ("X",),  # close TradedGoods
            ("X",),  # close EventBuffer
            ("X",),  # close ConstructionAI
            ("X",),  # close <1>
            ("X",),  # close objects
            ("X",),  # close GameObject
        ]
        inner = minimal_v3(tags=inner_tags, attribs=inner_attribs, events=events)

        outer = wrap_as_outer([inner])
        section = parse_tag_section(outer, detect_version(outer))
        triples = list(Anno117Interpreter().find_traded_goods(outer, section))
        assert triples == []


class TestMultipleRowsInSingleTradedGoods:
    """TradedGoods 直下の child 要素ごとに triple を emit する．"""

    def test_emits_each_child_row(self) -> None:
        from tests.parser.filedb.conftest import minimal_v3

        tags = {
            2: "PassiveTrade",
            3: "History",
            4: "TradeRouteEntries",
            5: "TradedGoods",
            6: "AreaInfo",
        }
        attribs = {
            0x8001: "RouteID",
            0x8002: "GoodGuid",
            0x8003: "GoodAmount",
            0x8004: "TotalPrice",
            0x8005: "CityName",
        }
        events = [
            ("T", 6),  # AreaInfo
            ("T", 1),  # AreaInfo > <1> (player island)
            ("A", 0x8005, "プレイヤー島".encode("utf-16-le")),
            ("T", 2),
            ("T", 3),
            ("T", 4),
            ("T", 1),  # outer <1>
            ("T", 1),  # inner <1>
            ("A", 0x8001, struct.pack("<i", 42)),  # RouteID=42 on inner entry
            ("T", 5),  # TradedGoods
            ("T", 1),
            ("A", 0x8002, struct.pack("<i", 2088)),
            ("A", 0x8003, struct.pack("<i", 5)),
            ("A", 0x8004, struct.pack("<i", 0)),
            ("X",),  # close row #1
            ("T", 1),
            ("A", 0x8002, struct.pack("<i", 2073)),
            ("A", 0x8003, struct.pack("<i", -2)),
            ("A", 0x8004, struct.pack("<i", 0)),
            ("X",),  # close row #2
            ("X",),  # close TradedGoods
            ("X",),  # close inner <1>
            ("X",),  # close outer <1>
            ("X",),  # close TradeRouteEntries
            ("X",),  # close History
            ("X",),  # close PassiveTrade
            ("X",),  # close AreaInfo > <1>
            ("X",),  # close AreaInfo
        ]
        inner = minimal_v3(tags=tags, attribs=attribs, events=events)
        outer = wrap_as_outer([inner])
        section = parse_tag_section(outer, detect_version(outer))
        triples = list(Anno117Interpreter().find_traded_goods(outer, section))
        assert len(triples) == 2
        assert {(t.good_guid, t.amount) for t in triples} == {(2088, 5), (2073, -2)}
        assert {t.context.route_id for t in triples} == {"42"}
