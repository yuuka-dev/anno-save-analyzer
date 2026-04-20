"""GameInterpreter の基底定義．

各 title 実装は ``find_traded_goods`` で raw triple を yield し，
``extract.normalise`` 側で TradeEvent に組み立てる．
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..models import GameTitle, PartnerKind

if TYPE_CHECKING:
    from anno_save_analyzer.parser.filedb import TagSection


@dataclass(frozen=True)
class ExtractionContext:
    """raw triple を伴う付随コンテキスト．interpreter が埋める．"""

    session_id: str | None = None
    route_id: str | None = None
    partner_id: str | None = None
    partner_kind: PartnerKind = "unknown"
    timestamp_tick: int | None = None
    island_name: str | None = None
    """プレイヤー保有島の ``CityName``．NPC 島は事前に filter されているので
    ここに載るのは全てプレイヤー所有．interpreter が AreaInfo > <1> walk 時に
    attach する．Anno 117 で実測．Anno 1800 でも同構造なら取れるはず (v0.3.1 は
    117 のみ対象)．
    """


@dataclass(frozen=True)
class RawTradedGoodTriple:
    """``<TradedGoods>`` 直下の 1 アイテム．type 解釈は extract 層で行う．"""

    good_guid: int
    amount: int
    total_price: int
    context: ExtractionContext


class GameInterpreter(ABC):
    """title 固有の抽出戦略．"""

    title: GameTitle

    @abstractmethod
    def find_traded_goods(
        self,
        outer_filedb: bytes,
        outer_section: TagSection,
    ) -> Iterator[RawTradedGoodTriple]:
        """outer FileDB を起点に inner session を辿り raw triple を yield する．"""


def select_interpreter(title: GameTitle) -> GameInterpreter:
    """title に対応する interpreter を返す．"""
    from .anno117 import Anno117Interpreter
    from .anno1800 import Anno1800Interpreter

    mapping: dict[GameTitle, type[GameInterpreter]] = {
        GameTitle.ANNO_117: Anno117Interpreter,
        GameTitle.ANNO_1800: Anno1800Interpreter,
    }
    return mapping[title]()
